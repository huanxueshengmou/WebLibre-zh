/*
 * Copyright (c) 2024-2026 Fabian Freund.
 *
 * This file is part of WebLibre
 * (see https://weblibre.eu).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_material_design_icons/flutter_material_design_icons.dart';
import 'package:flutter_mozilla_components/flutter_mozilla_components.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:weblibre/core/design/app_colors.dart';
import 'package:weblibre/core/routing/routes.dart';
import 'package:weblibre/features/app_links/domain/entities/app_link_rule.dart';
import 'package:weblibre/features/app_links/domain/entities/context_app_link_policy.dart';
import 'package:weblibre/features/app_links/presentation/widgets/container_app_link_settings_dialog.dart';
import 'package:weblibre/features/geckoview/features/tabs/data/entities/child_tab_placement.dart';
import 'package:weblibre/features/geckoview/features/tabs/data/models/container_data.dart';
import 'package:weblibre/features/geckoview/features/tabs/domain/providers.dart';
import 'package:weblibre/features/geckoview/features/tabs/domain/providers/selected_container.dart';
import 'package:weblibre/features/settings/presentation/controllers/save_settings.dart';
import 'package:weblibre/features/settings/presentation/widgets/settings_detail.dart';
import 'package:weblibre/features/user/data/models/general_settings.dart';
import 'package:weblibre/features/user/domain/repositories/general_settings.dart';
import 'package:weblibre/i18n/i18n.dart';

const List<SettingsSectionDefinition> browsingSettingsSections = [
  SettingsSectionDefinition(
    title: 'Tabs',
    entries: [
      SettingsEntryDefinition(
        title: 'New Tab Default',
        subtitle: 'Choose the default type for manually created tabs',
        keywords: ['regular', 'private', 'isolated'],
        child: _NewTabDefaultSection(),
      ),
      SettingsEntryDefinition(
        title: 'Small Web Tab Default',
        subtitle: 'Choose the tab type used when entering Small Web',
        keywords: ['regular', 'private', 'isolated'],
        child: _SmallWebTabDefaultSection(),
      ),
      SettingsEntryDefinition(
        title: 'Tab List Direction',
        subtitle: 'Choose how tabs are ordered in the list view',
        keywords: ['sorting', 'order'],
        child: _TabListDirectionSection(),
      ),
      SettingsEntryDefinition(
        title: 'Tab Bar Direction',
        subtitle: 'Choose how tabs are ordered in the tab bar',
        keywords: ['sorting', 'order'],
        child: _TabBarDirectionSection(),
      ),
      SettingsEntryDefinition(
        title: 'New Child Tab Position',
        subtitle: 'Choose where tabs opened from another tab are inserted',
        keywords: [
          'child tabs',
          'new tab',
          'position',
          'order',
          'end of list',
          'after parent',
        ],
        child: _ChildTabPlacementSection(),
      ),
      SettingsEntryDefinition(
        title: 'Show Container UI',
        subtitle: 'Show container selectors, menus, and management',
        keywords: ['containers'],
        child: _ShowContainerUiTile(),
      ),
      SettingsEntryDefinition(
        title: 'Show Isolated Tab UI',
        subtitle: 'Show isolated-tab creation options in the UI',
        keywords: ['isolated tabs'],
        child: _ShowIsolatedTabUiTile(),
      ),
      SettingsEntryDefinition(
        title: 'Create Child Tabs',
        subtitle: 'Open links from tabs in the same container context',
        keywords: ['child tabs'],
        child: _CreateChildTabsTile(),
      ),
      SettingsEntryDefinition(
        title: 'Background Tab Behavior',
        subtitle: 'Choose what happens after a tab opens in the background',
        keywords: ['switch', 'background', 'new tab', 'snackbar', 'prompt'],
        child: _BackgroundTabOpenSection(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Navigation',
    entries: [
      SettingsEntryDefinition(
        title: 'Pull to Refresh',
        subtitle: 'Swipe down on pages to reload them',
        keywords: ['reload'],
        child: _PullToRefreshTile(),
      ),
      SettingsEntryDefinition(
        title: 'Double Back to Close Tab',
        subtitle: 'Require double back press before closing the current tab',
        keywords: ['back button'],
        child: _DoubleBackCloseTabTile(),
      ),
      SettingsEntryDefinition(
        title: 'Tab Bar Swipes',
        subtitle: 'Choose what swipes on the tab bar do',
        keywords: ['gestures', 'swipe', 'tab bar swipe behavior'],
        child: _TabBarSwipesLinkTile(),
      ),
      SettingsEntryDefinition(
        title: 'Sequential Tab Navigation',
        subtitle: 'Choose where stepping through tabs in order ends',
        keywords: [
          'gestures',
          'swipe',
          'next tab',
          'previous tab',
          'containers',
          'loop',
          'wrap around',
        ],
        child: _SequentialTabNavigationSection(),
      ),
      SettingsEntryDefinition(
        title: 'Open Links in Apps',
        subtitle: 'Choose how external app links open',
        keywords: ['app links', 'external apps'],
        child: _AppLinksModeSection(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Desktop Mode',
    entries: [
      SettingsEntryDefinition(
        title: 'Always Request Desktop Site',
        subtitle: 'Open new tabs in desktop mode by default',
        keywords: ['desktop mode', 'user agent', 'mobile site', 'tablet'],
        child: _GlobalDesktopModeTile(),
      ),
      SettingsEntryDefinition(
        title: 'Desktop Mode Sites',
        subtitle: 'Sites that always load in desktop mode',
        keywords: ['desktop mode', 'per-site', 'user agent', 'exceptions'],
        child: _DesktopModeSitesTile(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Home Screen',
    entries: [
      SettingsEntryDefinition(
        title: 'Install Sites as Apps',
        subtitle: 'Allow websites without a manifest to be installed as apps',
        keywords: ['pwa', 'web apps'],
        child: _AllowNonManifestPwaInstallTile(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'External Links',
    entries: [
      SettingsEntryDefinition(
        title: 'External Link Handling',
        subtitle: 'Choose how external links open in WebLibre',
        keywords: ['intents'],
        child: _ExternalLinkHandlingSection(),
      ),
      SettingsEntryDefinition(
        title: 'Custom Tabs',
        subtitle:
            'Let other apps open links in a lightweight in-app tab, instead '
            'of the main browser',
        keywords: [
          'custom tabs',
          'in-app browser',
          'chrome custom tabs',
          'external app',
          'share',
        ],
        child: _CustomTabsTile(),
      ),
      SettingsEntryDefinition(
        title: 'URL Cleaner',
        subtitle: 'Tracking removal rules and catalog updates',
        keywords: ['utm', 'tracking parameters'],
        child: _UrlCleanerSettingsTile(),
      ),
      SettingsEntryDefinition(
        title: 'Unshortener',
        subtitle: 'Short link resolver and API token',
        keywords: ['short links', 'redirects'],
        child: _UnshortenerSettingsTile(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Bookmarks',
    entries: [
      SettingsEntryDefinition(
        title: 'Bookmark Open Behavior',
        subtitle: 'Choose how tapping a bookmark opens it',
        keywords: ['bookmarks', 'open', 'custom tab', 'isolated'],
        child: _BookmarkOpenBehaviorSection(),
      ),
    ],
  ),
];

class BrowsingSettingsScreen extends StatelessWidget {
  const BrowsingSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SettingsDetailScaffold(
      title: tr("Browsing"),
      subtitle: tr("Tabs, navigation, app links, and Small Web behavior."),
      icon: MdiIcons.compassOutline,
      sections: browsingSettingsSections,
    );
  }
}

class _NewTabDefaultSection extends HookConsumerWidget {
  const _NewTabDefaultSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appColors = AppColors.of(context);
    final settings = ref.watch(generalSettingsWithDefaultsProvider);
    final defaultCreateTabType = settings.effectiveDefaultCreateTabType;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("New Tab Default")),
            subtitle: Text(tr("Choose the default type for manually created tabs")),
            leading: Icon(MdiIcons.tab),
            contentPadding: EdgeInsets.zero,
          ),
          Center(
            child: SegmentedButton(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(
                  value: TabType.regular,
                  label: Text(tr("Regular")),
                  icon: Icon(MdiIcons.tab),
                ),
                ButtonSegment(
                  value: TabType.private,
                  label: Text(tr("Private")),
                  icon: Icon(
                    MdiIcons.dominoMask,
                    color: defaultCreateTabType == TabType.private
                        ? null
                        : appColors.privateTabPurple,
                  ),
                ),
                if (settings.showIsolatedTabUi)
                  ButtonSegment(
                    value: TabType.isolated,
                    label: Text(tr("Isolated")),
                    icon: Icon(
                      MdiIcons.snowflake,
                      color: defaultCreateTabType == TabType.isolated
                          ? null
                          : appColors.isolatedTabTeal,
                    ),
                  ),
              ],
              selected: {defaultCreateTabType},
              onSelectionChanged: (value) async {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) => currentSettings.copyWith
                          .storedDefaultCreateTabType(value.first),
                    );
              },
              style: switch (defaultCreateTabType) {
                TabType.regular => null,
                TabType.private => SegmentedButton.styleFrom(
                  selectedBackgroundColor: appColors.privateSelectionOverlay,
                ),
                TabType.child => null,
                TabType.isolated => SegmentedButton.styleFrom(
                  selectedBackgroundColor: appColors.isolatedSelectionOverlay,
                ),
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SmallWebTabDefaultSection extends HookConsumerWidget {
  const _SmallWebTabDefaultSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appColors = AppColors.of(context);
    final settings = ref.watch(generalSettingsWithDefaultsProvider);
    final smallWebTabType = settings.effectiveSmallWebTabType;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("Small Web Tab Default")),
            subtitle: Text(tr("Choose the tab type used when entering Small Web")),
            leading: Icon(Icons.explore),
            contentPadding: EdgeInsets.zero,
          ),
          Center(
            child: SegmentedButton(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(
                  value: TabType.regular,
                  label: Text(tr("Regular")),
                  icon: Icon(MdiIcons.tab),
                ),
                ButtonSegment(
                  value: TabType.private,
                  label: Text(tr("Private")),
                  icon: Icon(
                    MdiIcons.dominoMask,
                    color: smallWebTabType == TabType.private
                        ? null
                        : appColors.privateTabPurple,
                  ),
                ),
                if (settings.showIsolatedTabUi)
                  ButtonSegment(
                    value: TabType.isolated,
                    label: Text(tr("Isolated")),
                    icon: Icon(
                      MdiIcons.snowflake,
                      color: smallWebTabType == TabType.isolated
                          ? null
                          : appColors.isolatedTabTeal,
                    ),
                  ),
              ],
              selected: {smallWebTabType},
              onSelectionChanged: (value) async {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) =>
                          currentSettings.copyWith.smallWebTabType(value.first),
                    );
              },
              style: switch (smallWebTabType) {
                TabType.regular => null,
                TabType.private => SegmentedButton.styleFrom(
                  selectedBackgroundColor: appColors.privateSelectionOverlay,
                ),
                TabType.child => null,
                TabType.isolated => SegmentedButton.styleFrom(
                  selectedBackgroundColor: appColors.isolatedSelectionOverlay,
                ),
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ExternalLinkHandlingSection extends HookConsumerWidget {
  const _ExternalLinkHandlingSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(generalSettingsWithDefaultsProvider);
    final tabIntentOpenSetting = settings.tabIntentOpenSetting;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("External Link Handling")),
            subtitle: Text(tr("Choose how external links open in WebLibre")),
            leading: Icon(MdiIcons.tabPlus),
            contentPadding: EdgeInsets.zero,
          ),
          RadioGroup(
            groupValue: tabIntentOpenSetting,
            onChanged: (value) async {
              if (value != null) {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) =>
                          currentSettings.copyWith.tabIntentOpenSetting(value),
                    );
              }
            },
            child: Column(
              children: [
                RadioListTile.adaptive(
                  value: TabIntentOpenSetting.ask,
                  title: Text(tr("Prompt")),
                  subtitle: Text(tr("Ask how external links should open")),
                  secondary: Icon(MdiIcons.messageQuestion),
                ),
                RadioListTile.adaptive(
                  value: TabIntentOpenSetting.regular,
                  title: Text(tr("Regular")),
                  subtitle: Text(tr("Open external links in a regular tab")),
                  secondary: Icon(MdiIcons.tab),
                ),
                RadioListTile.adaptive(
                  value: TabIntentOpenSetting.private,
                  title: Text(tr("Private")),
                  subtitle: Text(tr("Open external links in a private tab")),
                  secondary: Icon(
                    MdiIcons.dominoMask,
                    color: AppColors.of(context).privateTabPurple,
                  ),
                ),
                if (settings.showIsolatedTabUi)
                  RadioListTile.adaptive(
                    value: TabIntentOpenSetting.isolated,
                    title: Text(tr("Isolated")),
                    subtitle: Text(
                      tr("Open external links in an isolated tab"),
                    ),
                    secondary: Icon(
                      MdiIcons.snowflake,
                      color: AppColors.of(context).isolatedTabTeal,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BookmarkOpenBehaviorSection extends HookConsumerWidget {
  const _BookmarkOpenBehaviorSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(generalSettingsWithDefaultsProvider);
    final bookmarkOpenSetting = settings.effectiveBookmarkOpenSetting;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("Bookmark Open Behavior")),
            subtitle: Text(tr("Choose how tapping a bookmark opens it")),
            leading: Icon(MdiIcons.bookmarkMultiple),
            contentPadding: EdgeInsets.zero,
          ),
          RadioGroup(
            groupValue: bookmarkOpenSetting,
            onChanged: (value) async {
              if (value != null) {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) =>
                          currentSettings.copyWith.bookmarkOpenSetting(value),
                    );
              }
            },
            child: Column(
              children: [
                RadioListTile.adaptive(
                  value: BookmarkOpenSetting.ask,
                  title: Text(tr("Prompt")),
                  subtitle: Text(tr("Ask how the bookmark should open")),
                  secondary: Icon(MdiIcons.messageQuestion),
                ),
                RadioListTile.adaptive(
                  value: BookmarkOpenSetting.regular,
                  title: Text(tr("Regular")),
                  subtitle: Text(tr("Open the bookmark in a regular tab")),
                  secondary: Icon(MdiIcons.tab),
                ),
                RadioListTile.adaptive(
                  value: BookmarkOpenSetting.private,
                  title: Text(tr("Private")),
                  subtitle: Text(tr("Open the bookmark in a private tab")),
                  secondary: Icon(
                    MdiIcons.dominoMask,
                    color: AppColors.of(context).privateTabPurple,
                  ),
                ),
                RadioListTile.adaptive(
                  value: BookmarkOpenSetting.customTab,
                  title: Text(tr("Custom Tab")),
                  subtitle: Text(
                    tr("Open the bookmark in a lightweight custom tab"),
                  ),
                  secondary: Icon(MdiIcons.applicationOutline),
                ),
                if (settings.showIsolatedTabUi)
                  RadioListTile.adaptive(
                    value: BookmarkOpenSetting.isolated,
                    title: Text(tr("Isolated")),
                    subtitle: Text(
                      tr("Open the bookmark in an isolated tab"),
                    ),
                    secondary: Icon(
                      MdiIcons.snowflake,
                      color: AppColors.of(context).isolatedTabTeal,
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TabListDirectionSection extends HookConsumerWidget {
  const _TabListDirectionSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final direction = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.tabListDirection),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("Tab List Direction")),
            subtitle: Text(
              tr("Choose whether the newest tab appears at the top or bottom of the tab list"),
            ),
            leading: Icon(MdiIcons.formatListBulleted),
            contentPadding: EdgeInsets.zero,
          ),
          Center(
            child: SegmentedButton(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(
                  value: TabDirection.newestFirst,
                  label: Text(tr("Newest first")),
                  icon: Icon(MdiIcons.arrowCollapseUp),
                ),
                ButtonSegment(
                  value: TabDirection.oldestFirst,
                  label: Text(tr("Oldest first")),
                  icon: Icon(MdiIcons.arrowCollapseDown),
                ),
              ],
              selected: {direction},
              onSelectionChanged: (value) async {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) => currentSettings.copyWith
                          .tabListDirection(value.first),
                    );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _TabBarDirectionSection extends HookConsumerWidget {
  const _TabBarDirectionSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final direction = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.tabBarDirection),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("Tab Bar Direction")),
            subtitle: Text(
              tr("Choose whether the newest tab appears on the left or right of the quick switcher"),
            ),
            leading: Icon(MdiIcons.reorderHorizontal),
            contentPadding: EdgeInsets.zero,
          ),
          Center(
            child: SegmentedButton(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(
                  value: TabDirection.newestFirst,
                  label: Text(tr("Newest first")),
                  icon: Icon(MdiIcons.arrowCollapseLeft),
                ),
                ButtonSegment(
                  value: TabDirection.oldestFirst,
                  label: Text(tr("Oldest first")),
                  icon: Icon(MdiIcons.arrowCollapseRight),
                ),
              ],
              selected: {direction},
              onSelectionChanged: (value) async {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) =>
                          currentSettings.copyWith.tabBarDirection(value.first),
                    );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ChildTabPlacementSection extends HookConsumerWidget {
  const _ChildTabPlacementSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final placement = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.childTabPlacement),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("New Child Tab Position")),
            subtitle: Text(
              tr("Choose whether a tab opened from another tab follows its opener or goes to the end. The opener is still remembered either way, so the tree view is unaffected"),
            ),
            leading: Icon(MdiIcons.fileTreeOutline),
            contentPadding: EdgeInsets.zero,
          ),
          Center(
            child: SegmentedButton(
              showSelectedIcon: false,
              segments: [
                ButtonSegment(
                  value: ChildTabPlacement.afterParent,
                  label: Text(tr("After opener")),
                  icon: Icon(MdiIcons.arrowRightBottom),
                ),
                ButtonSegment(
                  value: ChildTabPlacement.endOfList,
                  label: Text(tr("At the end")),
                  icon: Icon(MdiIcons.arrowCollapseDown),
                ),
              ],
              selected: {placement},
              onSelectionChanged: (value) async {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) => currentSettings.copyWith
                          .childTabPlacement(value.first),
                    );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _CreateChildTabsTile extends HookConsumerWidget {
  const _CreateChildTabsTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final createChildTabsOption = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.createChildTabsOption,
      ),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Create Child Tabs")),
      subtitle: Text(
        tr("Display a button to create a child tab under the current tab (tree view only)"),
      ),
      secondary: const Icon(MdiIcons.fileTree),
      value: createChildTabsOption,
      onChanged: (value) async {
        await ref
            .read(saveGeneralSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.createChildTabsOption(value),
            );
      },
    );
  }
}

class _ShowContainerUiTile extends HookConsumerWidget {
  const _ShowContainerUiTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final showContainerUi = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.showContainerUi),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Show Container UI")),
      subtitle: Text(tr("Show container selectors, menus, and management")),
      secondary: const Icon(MdiIcons.folder),
      value: showContainerUi,
      onChanged: (value) async {
        await ref.read(saveGeneralSettingsControllerProvider.notifier).save((
          currentSettings,
        ) {
          var updated = currentSettings.copyWith.showContainerUi(value);
          if (!value &&
              const {
                TabBarStackingMode.containerTabs,
                TabBarStackingMode.accordion,
                TabBarStackingMode.twoLevel,
              }.contains(updated.tabBarStackingMode)) {
            updated = updated.copyWith.tabBarStackingMode(
              TabBarStackingMode.lastUsedTabs,
            );
          }
          return updated;
        });

        if (!value) {
          ref.read(selectedContainerProvider.notifier).clearContainer();
        }
      },
    );
  }
}

class _ShowIsolatedTabUiTile extends HookConsumerWidget {
  const _ShowIsolatedTabUiTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final showIsolatedTabUi = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.showIsolatedTabUi),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Show Isolated Tab UI")),
      subtitle: Text(tr("Show isolated-tab creation options in the UI")),
      secondary: Icon(
        MdiIcons.snowflake,
        color: AppColors.of(context).isolatedTabTeal,
      ),
      value: showIsolatedTabUi,
      onChanged: (value) async {
        await ref.read(saveGeneralSettingsControllerProvider.notifier).save((
          currentSettings,
        ) {
          var updated = currentSettings.copyWith.showIsolatedTabUi(value);
          if (!value &&
              updated.storedDefaultCreateTabType == TabType.isolated) {
            updated = updated.copyWith.storedDefaultCreateTabType(
              TabType.regular,
            );
          }
          if (!value &&
              updated.tabIntentOpenSetting == TabIntentOpenSetting.isolated) {
            updated = updated.copyWith.tabIntentOpenSetting(
              TabIntentOpenSetting.ask,
            );
          }
          if (!value && updated.smallWebTabType == TabType.isolated) {
            updated = updated.copyWith.smallWebTabType(TabType.private);
          }
          if (!value &&
              updated.bookmarkOpenSetting == BookmarkOpenSetting.isolated) {
            updated = updated.copyWith.bookmarkOpenSetting(
              BookmarkOpenSetting.ask,
            );
          }
          return updated;
        });
      },
    );
  }
}

class _BackgroundTabOpenSection extends HookConsumerWidget {
  const _BackgroundTabOpenSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final backgroundTabOpenAction = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.backgroundTabOpenAction,
      ),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("Background Tab Behavior")),
            subtitle: Text(
              tr("Applies when an action opens a new tab in the background, e.g. \"Open in new tab\" or cloning a tab"),
            ),
            leading: Icon(MdiIcons.tabPlus),
            contentPadding: EdgeInsets.zero,
          ),
          RadioGroup(
            groupValue: backgroundTabOpenAction,
            onChanged: (value) async {
              if (value != null) {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) => currentSettings.copyWith
                          .backgroundTabOpenAction(value),
                    );
              }
            },
            child: Column(
              children: [
                RadioListTile.adaptive(
                  value: BackgroundTabOpenAction.prompt,
                  title: Text(tr("Stay and Offer to Switch")),
                  subtitle: Text(
                    tr("Keep the current tab and show a notice with a Switch action"),
                  ),
                ),
                RadioListTile.adaptive(
                  value: BackgroundTabOpenAction.switchImmediately,
                  title: Text(tr("Switch Immediately")),
                  subtitle: Text(tr("Jump straight to the newly opened tab")),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Tab bar swipes are configured with every other gesture, one binding per
/// direction; this entry only points there so the old place still finds them.
class _TabBarSwipesLinkTile extends StatelessWidget {
  const _TabBarSwipesLinkTile();

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: const Icon(MdiIcons.gestureSwipeHorizontal),
      title: Text(tr("Tab Bar Swipes")),
      subtitle: Text(tr("Choose what each swipe does in Gestures")),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => GestureSettingsRoute().push(context),
    );
  }
}

class _SequentialTabNavigationSection extends HookConsumerWidget {
  const _SequentialTabNavigationSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final crossContainers = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.sequentialTabNavigationCrossContainers,
      ),
    );
    final loop = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.sequentialTabNavigationLoop,
      ),
    );
    final showContainerUi = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.showContainerUi),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("Sequential Tab Navigation")),
            subtitle: Text(
              tr("Applies to the tab bar swipe and the next/previous tab gestures"),
            ),
            leading: Icon(MdiIcons.swapHorizontal),
            contentPadding: EdgeInsets.zero,
          ),
          if (showContainerUi)
            SwitchListTile.adaptive(
              title: Text(tr("Continue Into Next Container")),
              subtitle: Text(
                tr("Stepping past the first or last tab of a container moves into the neighbouring one. When off, navigation stays inside the current container."),
              ),
              secondary: const Icon(MdiIcons.folderMultipleOutline),
              contentPadding: EdgeInsets.zero,
              value: crossContainers,
              onChanged: (value) async {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (currentSettings) => currentSettings.copyWith
                          .sequentialTabNavigationCrossContainers(value),
                    );
              },
            ),
          SwitchListTile.adaptive(
            title: Text(tr("Loop Around")),
            subtitle: Text(
              tr("Stepping past the last tab continues at the first one, and the other way round."),
            ),
            secondary: const Icon(MdiIcons.repeat),
            contentPadding: EdgeInsets.zero,
            value: loop,
            onChanged: (value) async {
              await ref
                  .read(saveGeneralSettingsControllerProvider.notifier)
                  .save(
                    (currentSettings) => currentSettings.copyWith
                        .sequentialTabNavigationLoop(value),
                  );
            },
          ),
        ],
      ),
    );
  }
}

class _AppLinksModeSection extends HookConsumerWidget {
  const _AppLinksModeSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appLinksMode = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.appLinksMode),
    );
    final marketplaceFallback = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.appLinkMarketplaceFallback,
      ),
    );
    final authExceptionsEnabled = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.appLinkAuthExceptionsEnabled,
      ),
    );
    final blockWhilePrompting = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.appLinkBlockWhilePrompting,
      ),
    );
    final rules = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.appLinkRules),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            title: Text(tr("Open Links in Apps")),
            subtitle: Text(
              tr("Choose how links that can be opened in other apps are handled"),
            ),
            leading: Icon(MdiIcons.openInApp),
            contentPadding: EdgeInsets.zero,
          ),
          RadioGroup(
            groupValue: appLinksMode,
            onChanged: (value) async {
              if (value != null) {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save((current) => current.copyWith.appLinksMode(value));
              }
            },
            child: Column(
              children: [
                RadioListTile.adaptive(
                  value: AppLinksMode.always,
                  title: Text(tr("Always")),
                  subtitle: Text(
                    tr("Always open links in their native apps without asking"),
                  ),
                ),
                RadioListTile.adaptive(
                  value: AppLinksMode.ask,
                  title: Text(tr("Ask before opening")),
                  subtitle: Text(tr("Show a prompt before opening links in apps")),
                ),
                RadioListTile.adaptive(
                  value: AppLinksMode.never,
                  title: Text(tr("Never")),
                  subtitle: Text(
                    tr("Always open links in the browser instead of apps"),
                  ),
                ),
              ],
            ),
          ),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: Text(tr("Wait for your answer")),
            subtitle: Text(
              tr("Hold the page while asking, instead of loading it in the background. The site is not contacted unless you stay in the browser"),
            ),
            value: blockWhilePrompting,
            // Deliberately never disabled on the global mode. Prompts are not the
            // global mode's alone to grant: a protected container, a private tab
            // and a wallet scheme all prompt regardless of it, and a container
            // with isolated app-link settings can sit on `ask` while the global
            // mode is `never`. Greying this out under those modes would leave
            // blocking switched on with no way to switch it off.
            onChanged: (value) async {
              await ref
                  .read(saveGeneralSettingsControllerProvider.notifier)
                  .save(
                    (current) =>
                        current.copyWith.appLinkBlockWhilePrompting(value),
                  );
            },
          ),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: Text(tr("Offer app store fallback")),
            subtitle: Text(
              tr("When a link points to an app you don't have installed and there is no web fallback, offer to open the app store"),
            ),
            value: marketplaceFallback,
            onChanged: appLinksMode == AppLinksMode.never
                ? null
                : (value) async {
                    await ref
                        .read(saveGeneralSettingsControllerProvider.notifier)
                        .save(
                          (current) => current.copyWith
                              .appLinkMarketplaceFallback(value),
                        );
                  },
          ),
          SwitchListTile.adaptive(
            contentPadding: EdgeInsets.zero,
            title: Text(tr("Allow login app callbacks")),
            subtitle: Text(
              tr("Let apps that opened a Custom Tab receive their login callback, even when links are set to never open in apps"),
            ),
            value: authExceptionsEnabled,
            onChanged: (value) async {
              await ref
                  .read(saveGeneralSettingsControllerProvider.notifier)
                  .save(
                    (current) =>
                        current.copyWith.appLinkAuthExceptionsEnabled(value),
                  );
            },
          ),
          _AppLinkRulesSubsection(rules: rules),
          const _ContainerAppLinkOverridesSubsection(),
        ],
      ),
    );
  }
}

/// Containers running their own app-link policy (§ container isolation).
///
/// Their settings fully replace everything above for their tabs, and until now
/// the only way to reach one was through that container's own edit dialog — so a
/// container quietly set to "always" was invisible from the screen that claims to
/// govern app links. Listing them here says which containers are not covered by
/// the settings above, and opens the same editor.
class _ContainerAppLinkOverridesSubsection extends ConsumerWidget {
  const _ContainerAppLinkOverridesSubsection();

  static String _containerLabel(ContainerDataWithCount container) =>
      container.name ?? 'Container';

  String _modeLabel(AppLinksMode mode) => switch (mode) {
    AppLinksMode.always => tr("Always open in apps"),
    AppLinksMode.ask => tr("Asks before opening"),
    AppLinksMode.never => tr("Always keeps links in the browser"),
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final containers =
        ref.watch(watchContainersWithCountProvider).value ?? const [];
    final overrides = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.appLinkContextOverrides,
      ),
    );

    final isolated =
        containers
            .where(
              (container) =>
                  container.metadata.isolatedAppLinkSettings &&
                  container.metadata.contextualIdentity != null,
            )
            .toList()
          ..sort((a, b) => _containerLabel(a).compareTo(_containerLabel(b)));

    if (isolated.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(top: 16, bottom: 4),
          child: Text(tr("Containers with their own app-link settings")),
        ),
        for (final container in isolated)
          Builder(
            builder: (context) {
              final contextId = container.metadata.contextualIdentity!;
              final policy =
                  overrides[contextId] ?? ContextAppLinkPolicy.blank();
              final ruleCount = policy.rules.length;
              return ListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                leading: const Icon(MdiIcons.circleOutline),
                title: Text(_containerLabel(container)),
                subtitle: Text(
                  ruleCount == 0
                      ? _modeLabel(policy.mode)
                      : '${_modeLabel(policy.mode)} · $ruleCount remembered '
                            '${ruleCount == 1 ? 'rule' : 'rules'}',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => unawaited(
                  showDialog<void>(
                    context: context,
                    builder: (_) => ContainerAppLinkSettingsDialog(
                      contextId: contextId,
                      containerName: container.name,
                    ),
                  ),
                ),
              );
            },
          ),
      ],
    );
  }
}

/// Managed per-site app-link rules (§2.5): "always open" and "never open"
/// decisions the user remembered from a prompt. Read-only list with removal.
class _AppLinkRulesSubsection extends ConsumerWidget {
  final Map<String, PersistedAppLinkRule> rules;

  const _AppLinkRulesSubsection({required this.rules});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (rules.isEmpty) {
      return const SizedBox.shrink();
    }

    final entries = rules.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(top: 16, bottom: 4),
          child: Text(tr("Remembered site rules")),
        ),
        for (final MapEntry(:key, :value) in entries)
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: Icon(
              value.decision == AppLinkRuleDecision.alwaysOpen
                  ? MdiIcons.openInApp
                  : Icons.public,
            ),
            title: Text(displayAppLinkScope(key)),
            subtitle: Text(
              value.decision == AppLinkRuleDecision.alwaysOpen
                  ? tr("Always open in the app")
                  : tr("Always keep in the browser"),
            ),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline),
              tooltip: tr("Remove rule"),
              onPressed: () async {
                await ref
                    .read(saveGeneralSettingsControllerProvider.notifier)
                    .save(
                      (current) => current.copyWith.appLinkRules(
                        {...current.appLinkRules}..remove(key),
                      ),
                    );
              },
            ),
          ),
      ],
    );
  }
}

class _GlobalDesktopModeTile extends HookConsumerWidget {
  const _GlobalDesktopModeTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final globalDesktopMode = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.globalDesktopMode),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Always Request Desktop Site")),
      subtitle: Text(
        tr("Open new tabs in desktop mode by default. You can still toggle desktop mode per tab from the page menu."),
      ),
      secondary: const Icon(MdiIcons.monitor),
      value: globalDesktopMode,
      onChanged: (value) async {
        await ref
            .read(saveGeneralSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.globalDesktopMode(value),
            );
      },
    );
  }
}

class _DesktopModeSitesTile extends StatelessWidget {
  const _DesktopModeSitesTile();

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: const Icon(Icons.desktop_windows),
      title: Text(tr("Desktop Mode Sites")),
      subtitle: Text(tr("Sites that always load in desktop mode")),
      trailing: const Icon(Icons.chevron_right),
      onTap: () async {
        await const DesktopModeSitesRoute().push(context);
      },
    );
  }
}

class _PullToRefreshTile extends HookConsumerWidget {
  const _PullToRefreshTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pullToRefreshEnabled = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.pullToRefreshEnabled),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Pull to Refresh")),
      subtitle: Text(tr("Swipe down on pages to reload them")),
      secondary: const Icon(MdiIcons.gestureSwipeDown),
      value: pullToRefreshEnabled,
      onChanged: (value) async {
        await ref
            .read(saveGeneralSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.pullToRefreshEnabled(value),
            );
      },
    );
  }
}

class _CustomTabsTile extends HookConsumerWidget {
  const _CustomTabsTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final customTabsEnabled = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.customTabsEnabled),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Custom Tabs")),
      subtitle: Text(
        tr("Let other apps open links in a lightweight in-app tab. When off, these links and shared URLs open as normal tabs in the main browser."),
      ),
      secondary: const Icon(Icons.web_asset),
      value: customTabsEnabled,
      onChanged: (value) async {
        await ref
            .read(saveGeneralSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.customTabsEnabled(value),
            );
      },
    );
  }
}

class _DoubleBackCloseTabTile extends HookConsumerWidget {
  const _DoubleBackCloseTabTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final doubleBackCloseTab = ref.watch(
      generalSettingsWithDefaultsProvider.select((s) => s.doubleBackCloseTab),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Double Back to Close Tab")),
      subtitle: Text(
        tr("When enabled, press back twice to close the tab. When disabled, back button only navigates page history."),
      ),
      secondary: const Icon(MdiIcons.gestureDoubleTap),
      value: doubleBackCloseTab,
      onChanged: (value) async {
        await ref
            .read(saveGeneralSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.doubleBackCloseTab(value),
            );
      },
    );
  }
}

class _AllowNonManifestPwaInstallTile extends HookConsumerWidget {
  const _AllowNonManifestPwaInstallTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final allowNonManifestPwaInstall = ref.watch(
      generalSettingsWithDefaultsProvider.select(
        (s) => s.allowNonManifestPwaInstall,
      ),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Install Sites as Apps")),
      subtitle: Text(
        tr("Allow installing websites without a PWA manifest as standalone apps"),
      ),
      secondary: const Icon(Icons.add_to_home_screen),
      value: allowNonManifestPwaInstall,
      onChanged: (value) async {
        await ref
            .read(saveGeneralSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.allowNonManifestPwaInstall(value),
            );
      },
    );
  }
}

class _UrlCleanerSettingsTile extends StatelessWidget {
  const _UrlCleanerSettingsTile();

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: const Icon(MdiIcons.broom),
      title: Text(tr("URL Cleaner")),
      subtitle: Text(tr("Tracking removal rules and catalog updates")),
      trailing: const Icon(Icons.chevron_right),
      onTap: () async {
        await UrlCleanerSettingsRoute().push(context);
      },
    );
  }
}

class _UnshortenerSettingsTile extends StatelessWidget {
  const _UnshortenerSettingsTile();

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: const Icon(MdiIcons.linkVariant),
      title: Text(tr("Unshortener")),
      subtitle: Text(tr("Short link resolver and API token")),
      trailing: const Icon(Icons.chevron_right),
      onTap: () async {
        await UnshortenerSettingsRoute().push(context);
      },
    );
  }
}
