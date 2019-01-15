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
    __slots__ = ['root', 'name', 'topic_parts']

    def __init__(self, root: str, name: str, json_object: dict):
        self.root = root
        self.name = name
        self.topic_parts = map(
            lambda tp: TopicPart(tp) if json_object['topic_parts'][tp].get('c_type') is None else TopicPart(tp,
                                                                                                            json_object[
                                                                                                                'topic_parts'][
                                                                                                                tp][
                                                                                                                'c_type']),
            json_object['topic_parts'])

    def write(self, output_file):
        handler = codegen.CodeBlock()
        args = map(lambda tp: codegen.Argument(tp.name, tp.c_type), self.topic_parts)
        handler.function_prototype('%s_%s' % (self.root, self.name), output_file, static=True, args=args)


if __name__ == '__main__':
    args = codegen.create_args(TAG).parse_args()
    print("%s processing %s -> %s" % (TAG, args.input, args.output))

    output_file = open(args.output, 'w+')

    codegen.HeaderBlock(TAG, args.input).write(output_file)

    input = open(args.input)
    rpc_json = json.load(input)

    root = rpc_json['root']

    onmsg = codegen.CodeBlock()
    onmsg.function_prototype('%s_onmsg' % root, output_file)

    endpoints = []
    for endpoint in rpc_json['endpoints']:
        endpoint = Endpoint(root, endpoint, rpc_json['endpoints'][endpoint])
        endpoint.write(output_file)
        endpoints.append(endpoint)

    dispatch_args = []
    for k in ['context', 'request', 'response']:
        dispatch_args.append(codegen.Argument(k, rpc_json[k]['c_type']))
    dispatch_args[1:1] = [codegen.Argument('topicparts', 'const gchar**'), codegen.Argument('numtopicparts', 'int')]

    dispatch = codegen.CodeBlock()
    dispatch.start_function('__rpcgen_%s_dispatch' % root, output_file, static=True, args=dispatch_args)
    dispatch.add_statement('const gchar* endpoint = topicparts[0]', output_file)
    for endpoint in endpoints:
        dispatch.add_comment(endpoint.name, output_file)
        dispatch.start_or_alternative('0', output_file)
    dispatch.end_condition(output_file)
    dispatch.end_function(output_file)
