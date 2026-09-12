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
import 'package:flutter/material.dart';
import 'package:flutter_material_design_icons/flutter_material_design_icons.dart';
import 'package:flutter_mozilla_components/flutter_mozilla_components.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:weblibre/features/settings/presentation/controllers/save_settings.dart';
import 'package:weblibre/features/settings/presentation/widgets/settings_detail.dart';
import 'package:weblibre/features/user/data/models/engine_settings.dart';
import 'package:weblibre/features/user/domain/repositories/engine_settings.dart';
import 'package:weblibre/i18n/i18n.dart';

const List<SettingsSectionDefinition> customTrackingProtectionSections = [
  SettingsSectionDefinition(
    title: 'Allowlist Exceptions',
    entries: [
      SettingsEntryDefinition(
        title: 'Allowlist exceptions',
        subtitle: 'Compatibility exceptions for major and minor website issues',
        child: _AllowlistSection(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Cookies',
    entries: [
      SettingsEntryDefinition(
        title: 'Cookies',
        subtitle: 'Cookie blocking mode and policy selection',
        child: _CookiesSection(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Tracking Content',
    entries: [
      SettingsEntryDefinition(
        title: 'Tracking content',
        subtitle: 'Tracking scripts and scope for blocking',
        child: _TrackingContentSection(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Trackers',
    entries: [
      SettingsEntryDefinition(
        title: 'Trackers',
        subtitle: 'Cryptominers, known fingerprinters, and redirect trackers',
        child: _TrackersSection(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Advanced Fingerprinting Protection',
    entries: [
      SettingsEntryDefinition(
        title: 'Advanced fingerprinting protection',
        subtitle: 'Suspected fingerprinters and tab scope',
        child: _AdvancedFingerprintingSection(),
      ),
    ],
  ),
];

class CustomTrackingProtectionScreen extends StatelessWidget {
  const CustomTrackingProtectionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SettingsDetailScaffold(
      title: tr("Custom Tracking Protection"),
      subtitle: tr("Custom cookie, content, tracker, and fingerprinting controls."),
      icon: MdiIcons.shieldEditOutline,
      sections: customTrackingProtectionSections,
    );
  }
}

class _AllowlistSection extends HookConsumerWidget {
  const _AllowlistSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final allowListBaseline = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.allowListBaseline),
    );
    final allowListConvenience = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.allowListConvenience),
    );

    return Column(
      children: [
        SwitchListTile.adaptive(
          title: Text(tr("Fix website major issues")),
          subtitle: Text(
            tr("Apply exceptions required to avoid major website breakage (recommended)"),
          ),
          secondary: const Icon(MdiIcons.shieldCheck),
          value: allowListBaseline,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.allowListBaseline(value));
          },
        ),
        SwitchListTile.adaptive(
          title: Text(tr("Fix website minor issues")),
          subtitle: Text(
            tr("Apply exceptions to fix minor issues and enable convenience features"),
          ),
          secondary: const Icon(MdiIcons.shieldHalfFull),
          value: allowListConvenience,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.allowListConvenience(value));
          },
        ),
      ],
    );
  }
}

class _CookiesSection extends HookConsumerWidget {
  const _CookiesSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final blockCookies = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.blockCookies),
    );
    final customCookiePolicy = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.customCookiePolicy),
    );

    return Column(
      children: [
        SwitchListTile.adaptive(
          title: Text(tr("Block Cookies")),
          subtitle: Text(tr("Block cookies based on the policy below")),
          secondary: const Icon(MdiIcons.cookie),
          value: blockCookies,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.blockCookies(value));
          },
        ),
        if (blockCookies)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text(tr("Cookie Policy")),
                  contentPadding: EdgeInsets.zero,
                ),
                DropdownMenu<CustomCookiePolicy>(
                  initialSelection: customCookiePolicy,
                  width: double.infinity,
                  dropdownMenuEntries: [
                    DropdownMenuEntry(
                      value: CustomCookiePolicy.totalProtection,
                      label: tr("Total Cookie Protection (Recommended)"),
                      leadingIcon: Icon(MdiIcons.shieldLock),
                    ),
                    DropdownMenuEntry(
                      value: CustomCookiePolicy.crossSiteTrackers,
                      label: tr("Cross-site and social media trackers"),
                      leadingIcon: Icon(MdiIcons.accountGroup),
                    ),
                    DropdownMenuEntry(
                      value: CustomCookiePolicy.unvisited,
                      label: tr("Unvisited sites"),
                      leadingIcon: Icon(MdiIcons.webOff),
                    ),
                    DropdownMenuEntry(
                      value: CustomCookiePolicy.thirdParty,
                      label: tr("All third-party cookies"),
                      leadingIcon: Icon(MdiIcons.cookieOff),
                    ),
                    DropdownMenuEntry(
                      value: CustomCookiePolicy.allCookies,
                      label: tr("All cookies (may break sites)"),
                      leadingIcon: Icon(MdiIcons.cookieRemove),
                    ),
                  ],
                  onSelected: (value) async {
                    if (value != null) {
                      await ref
                          .read(saveEngineSettingsControllerProvider.notifier)
                          .save((s) => s.copyWith.customCookiePolicy(value));
                    }
                  },
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _TrackingContentSection extends HookConsumerWidget {
  const _TrackingContentSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final blockTrackingContent = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.blockTrackingContent),
    );
    final trackingContentScope = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.trackingContentScope),
    );

    return Column(
      children: [
        SwitchListTile.adaptive(
          title: Text(tr("Block Tracking Content")),
          subtitle: Text(
            tr("Block tracking scripts and resources embedded in websites"),
          ),
          secondary: const Icon(MdiIcons.scriptTextOutline),
          value: blockTrackingContent,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.blockTrackingContent(value));
          },
        ),
        if (blockTrackingContent)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text(tr("Apply to")),
                  contentPadding: EdgeInsets.zero,
                ),
                SizedBox(
                  width: double.infinity,
                  child: SegmentedButton<TrackingScope>(
                    segments: [
                      ButtonSegment(
                        value: TrackingScope.all,
                        label: Text(tr("All tabs")),
                      ),
                      ButtonSegment(
                        value: TrackingScope.privateOnly,
                        label: Text(tr("Private tabs only")),
                      ),
                    ],
                    selected: {trackingContentScope},
                    onSelectionChanged: (value) async {
                      await ref
                          .read(saveEngineSettingsControllerProvider.notifier)
                          .save(
                            (s) => s.copyWith.trackingContentScope(value.first),
                          );
                    },
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _TrackersSection extends HookConsumerWidget {
  const _TrackersSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final blockCryptominers = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.blockCryptominers),
    );
    final blockFingerprinters = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.blockFingerprinters),
    );
    final blockRedirectTrackers = ref.watch(
      engineSettingsWithDefaultsProvider.select((s) => s.blockRedirectTrackers),
    );
    final blockAdsAnalyticsSocialTrackers = ref.watch(
      engineSettingsWithDefaultsProvider.select(
        (s) => s.blockAdsAnalyticsSocialTrackers,
      ),
    );

    return Column(
      children: [
        SwitchListTile.adaptive(
          title: Text(tr("Ads, Analytics, and Social Trackers")),
          subtitle: Text(
            tr("Block advertising, analytics, social, and Mozilla social tracker categories"),
          ),
          secondary: const Icon(Icons.block),
          value: blockAdsAnalyticsSocialTrackers,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.blockAdsAnalyticsSocialTrackers(value));
          },
        ),
        SwitchListTile.adaptive(
          title: Text(tr("Cryptominers")),
          subtitle: Text(
            tr("Block scripts that use your device to mine cryptocurrency"),
          ),
          secondary: const Icon(MdiIcons.currencyBtc),
          value: blockCryptominers,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.blockCryptominers(value));
          },
        ),
        SwitchListTile.adaptive(
          title: Text(tr("Known Fingerprinters")),
          subtitle: Text(
            tr("Block scripts that collect information to uniquely identify your device"),
          ),
          secondary: const Icon(MdiIcons.fingerprint),
          value: blockFingerprinters,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.blockFingerprinters(value));
          },
        ),
        SwitchListTile.adaptive(
          title: Text(tr("Redirect Trackers")),
          subtitle: Text(
            tr("Block trackers that collect data through intermediate URL redirects"),
          ),
          secondary: const Icon(MdiIcons.routerNetwork),
          value: blockRedirectTrackers,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.blockRedirectTrackers(value));
          },
        ),
      ],
    );
  }
}

class _AdvancedFingerprintingSection extends HookConsumerWidget {
  const _AdvancedFingerprintingSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final blockSuspectedFingerprinters = ref.watch(
      engineSettingsWithDefaultsProvider.select(
        (s) => s.blockSuspectedFingerprinters,
      ),
    );
    final suspectedFingerprintersScope = ref.watch(
      engineSettingsWithDefaultsProvider.select(
        (s) => s.suspectedFingerprintersScope,
      ),
    );

    return Column(
      children: [
        SwitchListTile.adaptive(
          title: Text(tr("Suspected Fingerprinters")),
          subtitle: Text(
            tr("Block additional fingerprinting techniques that may be used to track you"),
          ),
          secondary: const Icon(MdiIcons.shieldSearch),
          value: blockSuspectedFingerprinters,
          onChanged: (value) async {
            await ref
                .read(saveEngineSettingsControllerProvider.notifier)
                .save((s) => s.copyWith.blockSuspectedFingerprinters(value));
          },
        ),
        if (blockSuspectedFingerprinters)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ListTile(
                  title: Text(tr("Apply to")),
                  contentPadding: EdgeInsets.zero,
                ),
                SizedBox(
                  width: double.infinity,
                  child: SegmentedButton<TrackingScope>(
                    segments: [
                      ButtonSegment(
                        value: TrackingScope.all,
                        label: Text(tr("All tabs")),
                      ),
                      ButtonSegment(
                        value: TrackingScope.privateOnly,
                        label: Text(tr("Private tabs only")),
                      ),
                    ],
                    selected: {suspectedFingerprintersScope},
                    onSelectionChanged: (value) async {
                      await ref
                          .read(saveEngineSettingsControllerProvider.notifier)
                          .save(
                            (s) => s.copyWith.suspectedFingerprintersScope(
                              value.first,
                            ),
                          );
                    },
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
