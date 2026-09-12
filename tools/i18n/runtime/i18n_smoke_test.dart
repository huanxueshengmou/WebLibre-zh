import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:weblibre/i18n/i18n.dart';
import 'package:weblibre/features/settings/presentation/widgets/settings_detail.dart';
import 'package:weblibre/features/proxy/presentation/widgets/profile_editor/profile_editor_section.dart';

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    binding.platformDispatcher.localesTestValue = const [
      Locale('zh'),
      Locale('en'),
    ];
    initI18n();
  });
  tearDown(() {
    setLanguageOverride(null);
    binding.platformDispatcher.clearLocalesTestValue();
  });

  test('phone locale and framework use the same ordered preference', () {
    expect(activeLanguage, 'zh');
    expect(tr('Cancel'), '取消');
    expect(
      resolveAppLocale(const [Locale('zh'), Locale('en')]),
      const Locale('zh'),
    );
    binding.platformDispatcher.localesTestValue = const [
      Locale('en'),
      Locale('zh'),
    ];
    expect(activeLanguage, 'en');
    expect(tr('Cancel'), 'Cancel');
    expect(
      resolveAppLocale(const [Locale('en'), Locale('zh')]),
      const Locale('en'),
    );
    expect(
      resolveAppLocale(const [Locale('fr'), Locale('zh')]),
      const Locale('zh'),
    );
  });

  test(
    'format once, keep arguments, preserve unknown text and null UI fields',
    () {
      setLanguageOverride('en');
      expect(tr('{0} / {1}', ['{1}', 'value']), '{1} / value');
      expect(tr('{0}', [null]), 'null');
      expect(
        tr('User supplied title not in dictionary'),
        'User supplied title not in dictionary',
      );
      expect(trNullable(null), isNull);
      setLanguageOverride('zh');
      expect(trNullable('Cancel'), '取消');
    },
  );

  test(
    'Chinese and English queries can both match unmodified settings data',
    () {
      const sections = [
        SettingsSectionDefinition(
          title: 'Overview',
          entries: [
            SettingsEntryDefinition(title: 'Cancel', child: SizedBox()),
          ],
        ),
      ];
      expect(sections.single.entries.single.title, 'Cancel');
      expect(
        filterSettingsSections(sections: sections, query: '取消'),
        hasLength(1),
      );
      expect(
        filterSettingsSections(sections: sections, query: 'cancel'),
        hasLength(1),
      );
      expect(
        filterSettingsSections(sections: sections, query: 'missing-query'),
        isEmpty,
      );
    },
  );

  testWidgets(
    'audited constant section titles and form headings render Chinese',
    (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            supportedLocales: const [Locale('en'), Locale('zh')],
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            localeListResolutionCallback: (locales, supported) =>
                resolveAppLocale(locales),
            home: const Scaffold(
              body: SingleChildScrollView(
                child: Column(
                  children: [
                    SettingsSectionList(
                      query: '',
                      sections: [
                        SettingsSectionDefinition(
                          title: 'Overview',
                          entries: [],
                        ),
                      ],
                    ),
                    ProfileEditorSection(
                      title: 'Protocol Options',
                      child: SizedBox(height: 12),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tr('Overview'), isNot('Overview'));
      expect(find.text(tr('Overview')), findsOneWidget);
      expect(tr('Protocol Options'), isNot('Protocol Options'));
      expect(find.text(tr('Protocol Options')), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
