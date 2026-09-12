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
/// The language is chosen from the device on first use, so a phone set to
/// Chinese gets Chinese with no configuration. [setLanguageOverride] lets the
/// user force a language regardless of the device.
library;

import 'dart:ui' as ui;

import 'zh_table.dart';

/// Languages we actually ship a translation table for.
const Set<String> kShippedLanguages = {'zh'};

String _deviceLanguage = 'en';
String? _override;
bool _ready = false;

/// The language [tr] is currently resolving against.
String get activeLanguage => _override ?? _deviceLanguage;

/// True when [tr] will actually translate rather than fall back to English.
bool get isTranslated => kShippedLanguages.contains(activeLanguage);

/// Read the device language. Safe to call before `runApp`; also safe to skip,
/// because [tr] initialises lazily on first use.
void initI18n({String? override}) {
  _override = (override == null || override.isEmpty) ? null : override;
  _deviceLanguage = _detectLanguage();
  _ready = true;
}

/// Force a language, or pass null to go back to following the device.
void setLanguageOverride(String? code) {
  _override = (code == null || code.isEmpty) ? null : code;
  _ready = true;
}

String _detectLanguage() {
  try {
    // The full preference list is ordered best-first, so honour it before
    // falling back to the single primary locale.
    for (final locale in ui.PlatformDispatcher.instance.locales) {
      final code = locale.languageCode.toLowerCase();
      if (kShippedLanguages.contains(code)) return code;
    }
    final primary =
        ui.PlatformDispatcher.instance.locale.languageCode.toLowerCase();
    if (kShippedLanguages.contains(primary)) return primary;
  } catch (_) {
    // PlatformDispatcher is not ready yet; English is a safe answer and the
    // next call will pick the real language up.
  }
  return 'en';
}

/// The table for the active language. Empty means "show English".
Map<String, String> get _table {
  switch (activeLanguage) {
    case 'zh':
      return kZhTable;
    default:
      return const <String, String>{};
  }
}

/// Translate [en], substituting `{0}`, `{1}` ... from [args].
///
/// Returns [en] unchanged when the active language is English or has no
/// translation for this key.
String tr(String en, [List<Object?>? args]) {
  if (!_ready) initI18n();

  var out = en;
  if (activeLanguage != 'en') {
    out = _table[en] ?? en;
  }

  if (args != null && args.isNotEmpty) {
    for (var i = 0; i < args.length; i++) {
      final value = args[i];
      if (value == null) continue;
      out = out.replaceAll('{$i}', '$value');
    }
  }
  return out;
}

/// Convenience for the rare place that wants the translation of a string that
/// is already in a variable rather than a literal.
String trText(String en, [List<Object?>? args]) => tr(en, args);
