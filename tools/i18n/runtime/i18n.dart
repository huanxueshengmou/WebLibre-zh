/// Runtime translation for WebLibre.
///
/// Every user-visible English string in the app was rewritten by the codemod in
/// `tools/i18n/codemod.py` to call [tr], with the original English kept as the
/// lookup key:
///
///     Text('Cancel')                    -> Text(tr("Cancel"))
///     Text('Remove $name from here?')   -> Text(tr("Remove {0} from here?", [name]))
///
/// Keeping English as the key has three useful consequences:
///   * nothing is ever lost - an untranslated string simply shows English
///   * a translation can be added or fixed without touching Dart source
///   * upstream updates never conflict, because the key is upstream's own text
///
/// 每次翻译读取当前系统语言偏好；[setLanguageOverride] 可指定语言。
/// 系统变化会在下一次调用时生效，但不会主动触发现有 UI 重绘。
library;

import 'dart:ui' as ui;

import 'package:flutter/widgets.dart' show WidgetsBinding;

import 'locale_policy.dart';
import 'zh_table.dart';

export 'locale_policy.dart' show resolveLanguageCodes;

/// 已提供翻译表的语言；英语为原文，由语言策略一起参与偏好匹配。
const Set<String> kShippedLanguages = {'zh'};

String? _override;

/// 未指定覆盖时，每次读取当前系统偏好，不缓存设备语言。
String get activeLanguage => _override ?? _detectLanguage();

/// True when [tr] will actually translate rather than fall back to English.
bool get isTranslated => kShippedLanguages.contains(activeLanguage);

/// 设置初始覆盖；可在 runApp 前调用，也可省略，默认跟随系统。
/// null、空白及不支持的语言均取消覆盖。
void initI18n({String? override}) {
  _override = normalizeLanguageOverride(override);
}

/// 指定语言；null、空白及不支持的语言均恢复跟随系统。
void setLanguageOverride(String? code) {
  _override = normalizeLanguageOverride(code);
}

String _detectLanguage() {
  try {
    // Respect Flutter's dispatcher abstraction (including test locale overrides).
    final dispatcher = WidgetsBinding.instance.platformDispatcher;
    final locales = dispatcher.locales;
    return resolveLanguageCodes(
      locales.isEmpty
          ? [dispatcher.locale.toLanguageTag()]
          : locales.map((locale) => locale.toLanguageTag()),
    );
  } catch (_) {
    // 平台尚未就绪时回落英语，下一次调用仍会重新检测。
    return 'en';
  }
}

/// Flutter's built-in widgets use exactly the same ordered language policy.
ui.Locale resolveAppLocale(List<ui.Locale>? locales) {
  final language =
      _override ??
      (locales == null || locales.isEmpty
          ? _detectLanguage()
          : resolveLanguageCodes(
              locales.map((locale) => locale.toLanguageTag()),
            ));
  return ui.Locale(language);
}

/// Translate an optional, audited UI field without turning null into text.
String? trNullable(String? en) => en == null ? null : tr(en);

/// The table for the active language. Empty means "show English".
Map<String, String> get _table {
  switch (activeLanguage) {
    case 'zh':
      return kZhTable;
    default:
      return const <String, String>{};
  }
}

/// 查找译文后，单遍替换 [args] 对应的 `{0}`、`{1}` 等占位符。
/// 英语或缺少译文时使用 [en]，仍执行参数插值；null 输出为 'null'。
String tr(String en, [List<Object?>? args]) {
  return formatTranslatedText(_table[en] ?? en, args);
}

/// Convenience for the rare place that wants the translation of a string that
/// is already in a variable rather than a literal.
String trText(String en, [List<Object?>? args]) => tr(en, args);
