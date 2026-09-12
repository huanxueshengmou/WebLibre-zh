// Small JSON bridge used to check the CI configuration without Python extras.
import 'dart:convert';
import 'dart:io';
import 'package:yaml/yaml.dart';

void main(List<String> args) {
  if (args.length != 1) throw ArgumentError('Expected one YAML file');
  stdout.write(jsonEncode(loadYaml(File(args.single).readAsStringSync())));
}
