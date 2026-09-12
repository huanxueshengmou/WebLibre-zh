// Parse without resolving Flutter dependencies. The official Dart AST, rather
// than punctuation heuristics, decides where runtime translations are legal.
import 'dart:convert';
import 'dart:io';

import 'package:analyzer/dart/analysis/features.dart';
import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/visitor.dart';
import 'package:analyzer/dart/ast/token.dart';

class ContextVisitor extends GeneralizingAstVisitor<void> {
  final blocks = <Map<String, Object>>[];
  final constants = <Map<String, Object>>[];
  final calls = <Map<String, Object>>[];
  final literals = <Map<String, Object>>[];

  void block(AstNode? node, String reason) {
    if (node != null) {
      blocks.add({'start': node.offset, 'end': node.end, 'reason': reason});
    }
  }

  void constant(AstNode node, Token? keyword) {
    if (keyword != null && keyword.lexeme == 'const') {
      constants.add({
        'start': node.offset,
        'end': node.end,
        'keyword_start': keyword.offset,
        'keyword_end': keyword.end,
      });
    }
  }

  @override
  void visitNode(AstNode node) {
    if (node is VariableDeclarationList && node.isConst) {
      block(node, 'const-var-decl');
    } else if (node is ConstructorDeclaration && node.constKeyword != null) {
      block(node, 'const-ctor-decl');
    } else if (node is FormalParameterDefaultClause) {
      block(node.value, 'parameter-default');
    } else if (node is Annotation) {
      block(node, 'annotation-arg');
    } else if (node is EnumConstantDeclaration) {
      block(node, 'enum-const-arg');
    } else if (node is ConstantPattern) {
      block(node, 'constant-pattern');
    }

    if (node is InstanceCreationExpression) {
      constant(node, node.keyword);
    } else if (node is ListLiteral) {
      constant(node, node.constKeyword);
    } else if (node is SetOrMapLiteral) {
      constant(node, node.constKeyword);
    } else if (node is RecordLiteral) {
      constant(node, node.constKeyword);
    }

    if (node is MethodInvocation &&
        node.target == null &&
        const {'tr', 'trText', 'trNullable'}.contains(node.methodName.name)) {
      calls.add({'start': node.offset, 'end': node.end});
    }
    // Export exact literal spans as well. Python may select UI text, but it
    // must never splice a range that the official parser does not call a string.
    if (node is StringLiteral) {
      literals.add({'start': node.offset, 'end': node.end});
    }
    super.visitNode(node);
  }
}

Future<void> main() async {
  final input = await stdin.transform(utf8.decoder).join();
  final sources = (jsonDecode(input) as Map<String, dynamic>);
  final result = <String, Object>{};
  for (final entry in sources.entries) {
    final parsed = parseString(
      content: entry.value as String,
      path: entry.key,
      featureSet: FeatureSet.latestLanguageVersion(),
      throwIfDiagnostics: false,
    );
    final visitor = ContextVisitor();
    parsed.unit.accept(visitor);
    result[entry.key] = {
      'blocks': visitor.blocks,
      'constants': visitor.constants,
      'calls': visitor.calls,
      'literals': visitor.literals,
      'errors': [
        for (final error in parsed.errors)
          {
            'start': error.offset,
            'end': error.offset + error.length,
            'message': error.message,
          },
      ],
    };
  }
  stdout.write(jsonEncode(result));
}
