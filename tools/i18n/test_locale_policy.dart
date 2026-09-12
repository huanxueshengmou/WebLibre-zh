import 'runtime/locale_policy.dart';

void main() {
  var checks = 0;

  void expectEqual(Object? actual, Object? expected, String label) {
    checks++;
    if (actual != expected) {
      throw StateError('$label：期望 <$expected>，实际 <$actual>');
    }
  }

  expectEqual(resolveLanguageCodes(['zh', 'en']), 'zh', '中文优先');
  expectEqual(resolveLanguageCodes(['en', 'zh']), 'en', '英文优先');
  expectEqual(resolveLanguageCodes(['fr', 'zh', 'en']), 'zh', '跳过未知语言');
  expectEqual(resolveLanguageCodes(['fr', 'en', 'zh']), 'en', '未知之后英文优先');
  expectEqual(resolveLanguageCodes(['fr', 'de', 'unknown']), 'en', '全部未知');
  expectEqual(resolveLanguageCodes([]), 'en', '空偏好列表');
  expectEqual(resolveLanguageCodes(['', '  ', 'und']), 'en', '空白及未定义语言');
  expectEqual(resolveLanguageCodes(['zh_Hans', 'en']), 'zh', '下划线脚本');
  expectEqual(resolveLanguageCodes(['ZH-hAnS-CN', 'en']), 'zh', '混合大小写及分段');
  expectEqual(resolveLanguageCodes(['en_US', 'zh_CN']), 'en', '下划线地区英文优先');
  expectEqual(resolveLanguageCodes(['zh-TW', 'en-US']), 'zh', '中文地区');
  expectEqual(resolveLanguageCodes(['en-GB', 'zh-CN']), 'en', '英文地区');
  expectEqual(resolveLanguageCodes(['  ZH_hant_HK  ']), 'zh', '空白及多段标签');
  expectEqual(resolveLanguageCodes(['en-US-u-hc-h12', 'zh']), 'en', '扩展子标签');
  expectEqual(resolveLanguageCodes(['english', 'zh']), 'zh', '不按英文前缀匹配');
  expectEqual(resolveLanguageCodes(['zhong', 'en']), 'en', '不按中文前缀匹配');
  expectEqual(resolveLanguageCodes(['x-zh', 'en']), 'en', '仅匹配首段语言');
  expectEqual(
    resolveLanguageCodes(['FR', 'ZH_cn'].map((code) => code)),
    'zh',
    '支持非 List 的 Iterable',
  );

  final preferences = ['en', 'zh'];
  expectEqual(resolveLanguageCodes(preferences), 'en', '首次偏好');
  preferences[0] = 'zh';
  preferences[1] = 'en';
  expectEqual(resolveLanguageCodes(preferences), 'zh', '偏好变化后重新解析');

  expectEqual(normalizeLanguageOverride('ZH_hAnS_CN'), 'zh', '覆盖规范化中文');
  expectEqual(normalizeLanguageOverride(' EN-us '), 'en', '覆盖规范化英文');
  expectEqual(normalizeLanguageOverride(null), null, 'null 取消覆盖');
  expectEqual(normalizeLanguageOverride(''), null, '空串取消覆盖');
  expectEqual(normalizeLanguageOverride('   '), null, '空白取消覆盖');
  expectEqual(normalizeLanguageOverride('fr-FR'), null, '未知覆盖返回 null');
  expectEqual(normalizeLanguageOverride('english'), null, '覆盖需完整首段匹配');
  expectEqual(
    normalizeLanguageOverride('fr') ?? resolveLanguageCodes(['zh', 'en']),
    'zh',
    '未知覆盖恢复跟随系统而非强制英语',
  );
  expectEqual(
    normalizeLanguageOverride('en-US') ?? resolveLanguageCodes(['zh']),
    'en',
    '有效覆盖优先于系统',
  );

  expectEqual(formatTranslatedText('原文'), '原文', '无参数');
  expectEqual(formatTranslatedText('{0}'), '{0}', '未提供参数列表');
  expectEqual(formatTranslatedText('{0}', null), '{0}', 'null 参数列表');
  expectEqual(formatTranslatedText('{0}', []), '{0}', '空参数列表');
  expectEqual(formatTranslatedText('', ['值']), '', '空文本');
  expectEqual(formatTranslatedText('原文', ['值']), '原文', '无占位符');
  expectEqual(
    formatTranslatedText('从 {1} 中移除 {0}', ['条目', '列表']),
    '从 列表 中移除 条目',
    '中文译文参数重排',
  );
  expectEqual(
    formatTranslatedText('Remove {0} from {1}', ['item', 'list']),
    'Remove item from list',
    '英文回落同样插值',
  );
  expectEqual(
    formatTranslatedText('{0} / {1}', ['{1}', '值']),
    '{1} / 值',
    '参数中的后续占位符不再替换',
  );
  expectEqual(
    formatTranslatedText('{1} / {0}', ['甲', '{0}']),
    '{0} / 甲',
    '参数中的先前占位符不再替换',
  );
  expectEqual(
    formatTranslatedText('{0}', ['{0}{1}', '值']),
    '{0}{1}',
    '参数中自身及其他占位符保持原样',
  );
  expectEqual(formatTranslatedText('值={0}', [null]), '值=null', 'null 参数插值');
  expectEqual(
    formatTranslatedText('{1}/{0}/{1}', [null, '值']),
    '值/null/值',
    '重排、重复和 null 混合',
  );
  expectEqual(formatTranslatedText('{0}{0}', [null]), 'nullnull', '重复 null');
  expectEqual(formatTranslatedText('{0}-{0}', ['值']), '值-值', '重复占位符');
  expectEqual(
    formatTranslatedText('{0} {1} {9}', ['值']),
    '值 {1} {9}',
    '索引等于或大于参数长度时保留',
  );
  expectEqual(
    formatTranslatedText('{999999999999999999999999999999}', ['值']),
    '{999999999999999999999999999999}',
    '超大索引保留而非抛异常',
  );
  expectEqual(
    formatTranslatedText('{10}|{1}|{0}', List.generate(11, (i) => '值$i')),
    '值10|值1|值0',
    '多位索引',
  );
  expectEqual(formatTranslatedText('{01}', ['甲', '乙']), '乙', '前导零按数字索引');
  expectEqual(
    formatTranslatedText('{-1} {x} {} {1.0} { 0 }', ['值']),
    '{-1} {x} {} {1.0} { 0 }',
    '非数字占位符保持原样',
  );
  expectEqual(formatTranslatedText('{0}/{1}', [42, true]), '42/true', '非字符串值');
  expectEqual(formatTranslatedText('前{0}后', ['']), '前后', '空串参数');
  expectEqual(
    formatTranslatedText('{0}', [r'$1\{1}']),
    r'$1\{1}',
    '参数中的美元符号和反斜杠保持原样',
  );

  print('通过 $checks 项 locale_policy 检查');
}
