from pycparser import parse_file
from pycparser.c_ast import Typedef, TypeDecl, Struct, Decl, IdentifierType, PtrDecl
from pycparser.c_ast import Enum as CEnum
from enum import Enum
import argparse


def annotation_type_from_field_name(field_name: str):
    return field_name[2:].split('_')[1]


def annotation_parameters_from_field_name(field_name: str):
    return field_name[2:].split('_')[2:]


class AnnotatedStruct:
    def __init__(self, struct_name: str, annotation_type: str, parameters: list):
        self.struct_name = struct_name
        self.annotation_type = annotation_type
        self.parameters = parameters


class FieldAnnotation:
    def __init__(self, field_name):
        self.annotation_type = annotation_type_from_field_name(field_name)
        all_parameters = annotation_parameters_from_field_name(field_name)
        self.field_name = all_parameters[0]
        self.parameters = all_parameters[1:]


class FieldType(Enum):
    NORMAL = 1
    POINTER = 2
    STRUCT = 3
    ENUM = 4


class Field:
    __slots__ = ['field', 'field_name', 'type', 'c_type', 'struct', 'enum', 'fields_and_annotations']

    def __init__(self, field: Decl, ast, tag, annotation_types):
        self.field = field
        self.field_name = field.name

        field_type = type(field.type)
        if field_type == TypeDecl:
            decl_type = type(field.type.type)
            if decl_type == IdentifierType:
                self.c_type = field.type.type.names[0]
                self.type = FieldType.NORMAL
            elif decl_type == Struct:
                self.type = FieldType.STRUCT
                self.c_type = field.type.type.name
                self.struct = struct_by_name(ast, self.c_type)
                self.fields_and_annotations = walk_struct(ast, tag, self.struct, annotation_types)
            elif decl_type == CEnum:
                self.type = FieldType.ENUM
                self.c_type = field.type.type.name
                self.enum = enum_by_name(ast, self.c_type)
            else:
                field.show()
                assert False, ("TypeDecl type %s not handled" % decl_type)
        elif field_type == PtrDecl:
            self.c_type = field.type.type.type.names[0]
            self.type = FieldType.POINTER
        else:
            assert False, ("field type %s not handled" % (type(field.type)))


class Argument:
    __slots__ = ['name', 'c_type']

    def __init__(self, name, c_type: str = 'void'):
        self.name = name
        self.c_type = c_type


class CodeBlock:
    __slots__ = ['indent', 'condition_started']

    def __init__(self):
        self.indent = 0
        self.condition_started = False

    def __do_indent(self, outputfile):
        tabs = '\t' * self.indent
        outputfile.write(tabs)

    def start_scope(self, outputfile, prefix=None):
        self.__do_indent(outputfile)
        if prefix is not None:
            outputfile.write(prefix)
        outputfile.write('{\n')
        self.indent += 1

    def __flatten_args(self, args: [Argument]):
        flattened_args = 'void'
        if args is not None:
            flattened_args = ", ".join(map(lambda a: "%s %s" % (a.c_type, a.name), args))
        return flattened_args

    def __static(self, static: bool):
        return 'static ' if static else ''

    def function_prototype(self, name, output_file, rtype: str = 'void', static=False, args: [Argument] = None):
        self.__do_indent(output_file)

        output_file.write('%s%s %s(%s);\n' % (self.__static(static), rtype, name, self.__flatten_args(args)))

    def start_function(self, name, output_file, rtype: str = 'void', static=False, args: [Argument] = None):
        self.start_scope(output_file,
                         '%s%s %s(%s)' % (self.__static(static), rtype, name, self.__flatten_args(args)))

    def end_scope(self, outputfile, terminate=False):
        self.indent -= 1
        self.__do_indent(outputfile)
        if terminate:
            outputfile.write('};\n')
        else:
            outputfile.write('}\n')

    def end_function(self, outputfile):
        self.end_scope(outputfile)

    def add_statement(self, statement: str, outputfile):
        self.__do_indent(outputfile)
        outputfile.write('%s;\n' % statement)

    def add_items(self, items: list, outputfile):
        for item in items:
            self.__do_indent(outputfile)
            outputfile.write('%s,\n' % item)

    def add_label(self, name: str, outputfile):
        self.__do_indent(outputfile)
        outputfile.write('%s:\n' % name)

    def add_break(self, outputfile):
        self.add_statement('break', outputfile)

    def write(self, outputfile):
        outputfile.write('// empty code block\n\n')

    # comments
    def add_comment(self, comment, outputfile):
        self.__do_indent(outputfile)
        outputfile.write('//%s\n' % comment)

    # conditions
    def start_condition(self, condition, outputfile):
        self.__do_indent(outputfile)
        outputfile.write('if(%s){\n' % condition)
        self.indent += 1
        self.condition_started = True

    def alternative_condition(self, condition, outputfile):
        self.indent -= 1
        self.__do_indent(outputfile)
        outputfile.write('}\n')
        self.__do_indent(outputfile)
        outputfile.write('else if(%s){\n' % condition)
        self.indent += 1

    def start_or_alternative(self, condition, outputfile):
        if self.condition_started:
            self.alternative_condition(condition, outputfile)
        else:
            self.start_condition(condition, outputfile)

    def add_else(self, outputfile):
        self.indent -= 1
        self.__do_indent(outputfile)
        outputfile.write('}\n')
        self.__do_indent(outputfile)
        outputfile.write('else {\n')
        self.indent += 1

    def end_condition(self, outputfile):
        self.indent -= 1
        self.__do_indent(outputfile)
        outputfile.write('}\n')
        self.condition_started = False


class HeaderBlock(CodeBlock):
    __slots__ = ['tag', 'input']

    def __init__(self, tag: str, input):
        self.tag = tag
        self.input = input

    def write(self, outputfile):
        outputfile.write("//generated by %s from %s\n" % (self.tag, self.input))


def __fulltag(tag: str):
    return '__%s' % tag


def parsefile(tag: str, input, headers):
    barrier = '-D__%s' % tag.upper()
    ast = parse_file(input, use_cpp=True,
                     cpp_args=[barrier, '-I/usr/share/python3-pycparser/fake_libc_include',
                               '-I%s' % headers])
    return ast


def find_annotated_structs(tag: str, annotation_types: list, ast):
    annotated_structs = []

    for child in ast.ext:
        if type(child) is Typedef:
            if child.name.startswith(__fulltag(tag)):
                name_parts = child.name[2:].split('_')

                assert len(name_parts) >= 2
                annotation_type = name_parts[1]
                assert annotation_type in annotation_types

                struct_name = child.type.type.name

                parameters = name_parts[2:]
                annotated_structs.append(AnnotatedStruct(struct_name, annotation_type, parameters))
                print("%s : %s -> %s" % (struct_name, annotation_type, str(parameters)))

    return annotated_structs


def find_structs(ast, callback, data):
    outputs = []
    for child in ast.ext:
        if type(child) is Decl:
            if type(child.type) is Struct:
                callback(ast, child.type, data, outputs)

    return outputs


def walk_struct(ast, tag: str, struct: Struct, annotation_types=[]):
    """
    walks a struct to find fields and annotations.
    :param ast:
    :param tag:
    :param struct:
    :param annotation_types:
    :return: a tuple of the fields and annotations that were found
    """
    annotations = []
    fields = []

    # bucket the fields and the annotations
    for field in struct:
        if field.name.startswith(__fulltag(tag)):
            print("found annotation %s" % field.name)
            assert annotation_type_from_field_name(field.name) in annotation_types
            annotations.append(FieldAnnotation(field.name))
        else:
            print("found field %s" % field.name)
            fields.append(Field(field, ast, tag, annotation_types))

    return fields, annotations


def struct_by_name(ast, name: (str)):
    print('looking for struct %s' % name)
    for child in ast:
        if type(child) is Decl:
            if type(child.type) is Struct:
                if child.type.name == name:
                    print('found struct %s' % name)
                    return child.type
    return None


def enum_by_name(ast, name: (str)):
    print('looking for enum %s' % name)
    for child in ast:
        if type(child) is Decl and type(child.type) is CEnum:
            return child.type
    return None


def create_args(tag: str):
    parser = argparse.ArgumentParser(description='%s code gen' % tag)
    parser.add_argument('--input', type=str, required=True)
    parser.add_argument('--output', type=str, required=True)
    parser.add_argument('--headers', type=str, required=True)
    return parser
