/// 按有序偏好选择首个支持的 en/zh；空列表或全部未知时回落 en。
String resolveLanguageCodes(Iterable<String> codes) {
  for (final code in codes) {
    final language = normalizeLanguageOverride(code);
    if (language != null) return language;
  }
  return 'en';
}

/// 统一大小写及下划线，按 BCP 47 首段语言匹配，忽略脚本、地区等后缀。
/// null、空白或不支持的语言返回 null，表示取消覆盖并跟随系统。
String? normalizeLanguageOverride(String? code) {
  final language = code
      ?.trim()
      .replaceAll('_', '-')
      .toLowerCase()
      .split('-')
      .first;
  return language == 'en' || language == 'zh' ? language : null;
}

final RegExp _placeholderPattern = RegExp(r'\{(\d+)\}');

/// 只替换输入文本中的占位符，不再解析参数内容；null 按 Dart 插值输出。
/// 越界或无法解析的索引保留原占位符。
String formatTranslatedText(String text, [List<Object?>? args]) {
  if (args == null || args.isEmpty) return text;
  return text.replaceAllMapped(_placeholderPattern, (match) {
    final index = int.tryParse(match.group(1)!);
    if (index == null || index >= args.length) return match.group(0)!;
    return '${args[index]}';
  });
}
