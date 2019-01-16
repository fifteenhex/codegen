#!/usr/bin/env python3

import codegen
import json

TAG = 'rpcgen'


class TopicPart:
    __slots__ = ['name', 'c_type', 'length', 'min', 'max', 'conversion']

    def __init__(self, name: str, c_type: str = 'const gchar*',
                 length: int = None, min: int = None, max: int = None,
                 conversion: str = None):
        self.name = name
        self.c_type = c_type
        self.length = length
        self.min = min
        self.max = max
        self.conversion = conversion

    @staticmethod
    def from_json(name: str, json: dict):
        t = TopicPart(name)
        for f in ['c_type', 'length', 'min', 'max', 'conversion']:
            if f in json:
                t.__setattr__(f, json[f])
        return t

    def define_var_and_check(self, index: int, codeblock: codegen.CodeBlock):
        if self.conversion is None:
            codeblock.add_statement('%s %s = topicparts[%d]' % (self.c_type, self.name, index))
            codeblock.start_scope()
            checked = False
            codeblock.add_statement('gsize %s_len = strlen(%s)' % (self.name, self.name))
            if self.length is not None:
                codeblock.start_condition('%s_len != %d' % (self.name, self.length))
                checked = True
            elif self.min is not None and self.max is not None:
                codeblock.start_condition(
                    '!(%s_len >= %d && %s_len <= %d)' % (self.name, self.min, self.name, self.max))
                checked = True
            # todo should probably assert here

            if checked:
                codeblock.add_statement('g_message("bad %s")' % self.name)
                codeblock.add_statement('ret = RPCGEN_ERR_BADTOPICPART')
                codeblock.add_statement('goto out')
                codeblock.end_condition()
            codeblock.end_scope()
        elif self.conversion == 'unsigned':
            codeblock.add_statement('%s %s' % (self.c_type, self.name))
            codeblock.start_scope()
            codeblock.add_statement('guint64 %s_tmp' % self.name)
            codeblock.start_condition('!g_ascii_string_to_unsigned(topicparts[%d], 10, %d, %d, &%s_tmp,NULL)' %
                                      (index, self.min, self.max, self.name))
            codeblock.add_statement('ret = RPCGEN_ERR_BADTOPICPART')
            codeblock.add_statement('goto out')
            codeblock.end_condition()
            codeblock.add_statement('%s = %s_tmp' % (self.name, self.name))
            codeblock.end_scope()


class Endpoint:
    __slots__ = ['root', 'name', 'topic_parts', 'shared_args']

    def __init__(self, root: str, name: str, json_object: dict, shared_args):
        self.root = root
        self.name = name
        self.topic_parts = list(map(lambda tp: TopicPart.from_json(tp, json_object['topic_parts'][tp]),
                                    json_object['topic_parts']))
        self.shared_args = shared_args

    def write(self, output_file):
        handler = codegen.CodeBlock(output_file)
        args = self.shared_args.copy()
        args[1:1] = map(lambda tp: codegen.Argument(tp.name, tp.c_type), self.topic_parts)
        handler.function_prototype(self.function_name(), static=True, args=args)

    def function_name(self):
        return '__%s_%s_%s' % (TAG, self.root, self.name)


if __name__ == '__main__':
    args = codegen.create_args(TAG).parse_args()
    print("%s processing %s -> %s" % (TAG, args.input, args.output))

    output_file = open(args.output, 'w+')

    codegen.HeaderBlock(TAG, args.input, output_file).write()

    includes = codegen.CodeBlock(output_file=output_file)
    includes.add_include('codegen/rpcgen.h')

    input = open(args.input)
    rpc_json = json.load(input)

    root = rpc_json['root']

    shared_args = []
    for k in ['context', 'request', 'response']:
        shared_args.append(codegen.Argument(k, rpc_json[k]['c_type']))
    dispatch_args = shared_args.copy()
    dispatch_args[1:1] = [codegen.Argument('topicparts', 'const gchar**'), codegen.Argument('numtopicparts', 'int')]

    endpoints = []
    for endpoint in rpc_json['endpoints']:
        endpoint = Endpoint(root, endpoint, rpc_json['endpoints'][endpoint], shared_args)
        endpoint.write(output_file)
        endpoints.append(endpoint)

    dispatch = codegen.CodeBlock(output_file=output_file)
    dispatch.start_function('__rpcgen_%s_dispatch' % root, static=True, rtype='int', args=dispatch_args)
    dispatch.add_statement('int ret = RPCGEN_ERR_NONE')
    dispatch.add_statement('const gchar* endpoint = topicparts[0]')
    for endpoint in endpoints:
        dispatch.start_or_alternative('g_strcmp0(endpoint, "%s") == 0' % endpoint.name)
        dispatch.add_comment(endpoint.name)
        dispatch.start_condition('(numtopicparts - 1) == %d' % len(endpoint.topic_parts))
        dispatch.add_statement(
            'g_message("incorrect number of topic parts for %s, expected %d and got %%d", numtopicparts)'
            % (endpoint.name, len(endpoint.topic_parts)))
        dispatch.add_statement('ret = RPCGEN_ERR_INVALIDTOPIC')
        dispatch.add_statement('goto out')
        dispatch.end_condition()
        for tp in endpoint.topic_parts:
            tp.define_var_and_check(1 + endpoint.topic_parts.index(tp), dispatch)
        call_args = ['context'] + list(map(lambda tp: tp.name, endpoint.topic_parts)) + ['request', 'response']
        dispatch.add_statement('%s(%s)' % (endpoint.function_name(), ', '.join(call_args)))
    dispatch.end_condition()
    dispatch.add_label('out')
    dispatch.add_statement('json_builder_set_member_name(response, "code")')
    dispatch.add_statement('json_builder_add_int_value(response, ret)')
    dispatch.add_statement('return ret')
    dispatch.end_function()
