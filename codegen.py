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
    class Type(Enum):
        NORMAL = 0
        CONDITION = 1

    __slots__ = ['indent', '__original_indent',
                 '__block_type', '__parent', '__sub_block',
                 'output_file']

    def __init__(self, output_file, indent: int = 0, block_type=Type.NORMAL, parent=None):
        self.indent = indent
        self.__original_indent = indent

        self.__block_type = block_type
        self.__parent = parent
        self.__sub_block = None

        self.output_file = output_file

    # indent handling

    def __do_indent(self):
        tabs = '\t' * self.indent
        self.output_file.write(tabs)

    def __inc_indent(self):
        self.indent += 1

    def __dec_indent(self):
        self.indent -= 1
        assert self.indent >= self.__original_indent

    # block chaining

    def __get_active_block(self):
        if self.__sub_block is not None:
            return self.__sub_block.__get_active_block()
        else:
            return self

    def __start_sub_block(self, block_type=Type.NORMAL):
        self.__inc_indent()
        self.__sub_block = CodeBlock(self.output_file, self.indent, block_type=block_type, parent=self)

    def __close_sub_block(self):
        assert self.__parent is not None
        cb = self.__parent
        cb.__dec_indent()
        cb.__do_indent()
        cb.output_file.write('}\n')
        cb.__sub_block = None

    def start_scope(self, prefix=None):
        self.__do_indent()
        if prefix is not None:
            self.output_file.write(prefix)
        self.output_file.write('{\n')
        self.__inc_indent()

    def __flatten_args(self, args: [Argument]):
        flattened_args = 'void'
        if args is not None:
            flattened_args = ", ".join(map(lambda a: "%s %s" % (a.c_type, a.name), args))
        return flattened_args

    def __static(self, static: bool):
        return 'static ' if static else ''

    def function_prototype(self, name, rtype: str = 'void', static=False, args: [Argument] = None):
        self.__do_indent()
        self.output_file.write('%s%s %s(%s);\n' % (self.__static(static), rtype, name, self.__flatten_args(args)))

    def start_function(self, name, rtype: str = 'void', static=False, args: [Argument] = None,
                       attributes: [str] = ['unused']):
        attributes_string = ' '.join(map(lambda a: '__attribute__((%s))' % a, attributes))
        self.start_scope(
            '%s%s %s %s(%s)' % (self.__static(static), rtype, attributes_string, name, self.__flatten_args(args)))

    def end_scope(self, terminate=False):
        self.__dec_indent()
        self.__do_indent()
        if terminate:
            self.output_file.write('};\n')
        else:
            self.output_file.write('}\n')

    def end_function(self):
        self.end_scope()

    def add_statement(self, statement: str):
        cb = self.__get_active_block()
        cb.__do_indent()
        cb.output_file.write('%s;\n' % statement)

    def add_include(self, path: str):
        self.__do_indent()
        self.output_file.write('#include <%s>\n' % path)

    def add_items(self, items: list):
        for item in items:
            self.__do_indent()
            self.output_file.write('%s,\n' % item)

    def add_label(self, name: str):
        self.__do_indent()
        self.output_file.write('%s:\n' % name)

    def add_break(self):
        self.add_statement('break')

    def write(self):
        self.output_file.write('// empty code block\n\n')

    # comments
    def add_comment(self, comment):
        self.__do_indent()
        self.output_file.write('//%s\n' % comment)

    # conditions
    def start_condition(self, condition):
        cb = self.__get_active_block()
        assert cb.__sub_block is None
        cb.__do_indent()
        cb.output_file.write('if(%s){\n' % condition)
        cb.__start_sub_block(block_type=CodeBlock.Type.CONDITION)

    @staticmethod
    def __alternative_condition(codeblock, condition):
        codeblock.__close_sub_block()
        # return to the parent and open up a new condition
        codeblock = codeblock.__parent
        codeblock.__do_indent()
        codeblock.output_file.write('else if(%s){\n' % condition)
        codeblock.__start_sub_block(block_type=CodeBlock.Type.CONDITION)

    def alternative_condition(self, condition):
        self.__alternative_condition(self.__get_active_block(), condition)

    def start_or_alternative(self, condition):
        cb = self.__get_active_block()
        if cb.__block_type == CodeBlock.Type.CONDITION:
            self.__alternative_condition(cb, condition)
        else:
            cb.start_condition(condition)

    def add_else(self):
        cb = self.__get_active_block()
        cb.__close_sub_block()

        cb = self.__get_active_block()
        cb.__do_indent()
        cb.output_file.write('else {\n')
        cb.__start_sub_block()

    def end_condition(self):
        cb = self.__get_active_block()
        cb.__close_sub_block()


class HeaderBlock(CodeBlock):
    __slots__ = ['tag', 'input']

    def __init__(self, tag: str, input, output_file):
        super(HeaderBlock, self).__init__(output_file)
        self.tag = tag
        self.input = input

    def write(self):
        self.output_file.write("//generated by %s from %s\n" % (self.tag, self.input))


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
