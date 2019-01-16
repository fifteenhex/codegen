#!/usr/bin/env python3

import codegen
import json

TAG = 'rpcgen'


class TopicPart:
    __slots__ = ['name', 'c_type']

    def __init__(self, name: str, c_type: str = 'const gchar*'):
        self.name = name
        self.c_type = c_type


class Endpoint:
    __slots__ = ['root', 'name', 'topic_parts', 'shared_args']

    def __init__(self, root: str, name: str, json_object: dict, shared_args):
        self.root = root
        self.name = name
        self.topic_parts = list(map(
            lambda tp: TopicPart(tp) if json_object['topic_parts'][tp].get('c_type') is None else TopicPart(tp,
                                                                                                            json_object[
                                                                                                                'topic_parts'][
                                                                                                                tp][
                                                                                                                'c_type']),
            json_object['topic_parts']))
        self.shared_args = shared_args

    def write(self, output_file):
        handler = codegen.CodeBlock(output_file)
        args = self.shared_args.copy()
        args[1:1] = map(lambda tp: codegen.Argument(tp.name, tp.c_type), self.topic_parts)
        handler.function_prototype(self.function_name(), static=True, args=args)

    def function_name(self):
        return '%s_%s' % (self.root, self.name)


if __name__ == '__main__':
    args = codegen.create_args(TAG).parse_args()
    print("%s processing %s -> %s" % (TAG, args.input, args.output))

    output_file = open(args.output, 'w+')

    codegen.HeaderBlock(TAG, args.input, output_file).write()

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
    dispatch.add_statement('int ret = 0')
    dispatch.add_statement('const gchar* endpoint = topicparts[0]')
    for endpoint in endpoints:
        dispatch.start_or_alternative('g_strcmp0(endpoint, "%s") == 0' % endpoint.name)
        dispatch.add_comment(endpoint.name)
        dispatch.start_condition('numtopicparts - 1 == %d' % len(endpoint.topic_parts))
        dispatch.end_condition()
        dispatch.add_statement('%s()' % endpoint.function_name())
    dispatch.end_condition()
    dispatch.add_statement('return ret')
    dispatch.end_function()
