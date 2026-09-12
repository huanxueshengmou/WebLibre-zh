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
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:weblibre/features/settings/presentation/controllers/save_settings.dart';
import 'package:weblibre/features/settings/presentation/widgets/settings_detail.dart';
import 'package:weblibre/features/user/data/models/engine_settings.dart';
import 'package:weblibre/features/user/domain/presentation/dialogs/quit_browser_dialog.dart';
import 'package:weblibre/features/user/domain/repositories/engine_settings.dart';
import 'package:weblibre/utils/exit_app.dart';
import 'package:weblibre/i18n/i18n.dart';

List<SettingsSectionDefinition> experimentalSettingsSections = [
  SettingsSectionDefinition(
    title: tr("Runtime & Startup"),
    entries: [
      SettingsEntryDefinition(
        title: tr("Isolated Content Process"),
        subtitle: tr("Run web content in an isolated process"),
        keywords: ['restart'],
        child: _IsolatedProcessEnabledTile(),
      ),
      SettingsEntryDefinition(
        title: tr("App Zygote Process"),
        subtitle: tr("Preload the content service for faster isolated startup"),
        keywords: ['restart', 'android 10'],
        child: _AppZygoteProcessEnabledTile(),
      ),
    ],
  ),
];

class ExperimentalSettingsScreen extends StatelessWidget {
  const ExperimentalSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SettingsDetailScaffold(
      title: 'Experimental',
      subtitle: tr("Runtime isolation and startup behavior."),
      icon: MdiIcons.flaskOutline,
      sections: experimentalSettingsSections,
    );
  }
}

class _IsolatedProcessEnabledTile extends HookConsumerWidget {
  const _IsolatedProcessEnabledTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isolatedProcessEnabled = ref.watch(
      engineSettingsWithDefaultsProvider.select(
        (s) => s.isolatedProcessEnabled,
      ),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("Isolated Content Process")),
      subtitle: Text(
        tr("Run web content in an isolated process. Requires app restart."),
      ),
      secondary: const Icon(MdiIcons.shieldCheck),
      value: isolatedProcessEnabled,
      onChanged: (value) async {
        await ref
            .read(saveEngineSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.isolatedProcessEnabled(value),
            );
        if (context.mounted) {
          await _showRestartDialog(context);
        }
      },
    );
  }
}

class _AppZygoteProcessEnabledTile extends HookConsumerWidget {
  const _AppZygoteProcessEnabledTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appZygoteProcessEnabled = ref.watch(
      engineSettingsWithDefaultsProvider.select(
        (s) => s.appZygoteProcessEnabled,
      ),
    );

    return SwitchListTile.adaptive(
      title: Text(tr("App Zygote Process")),
      subtitle: Text(
        tr("Preload the content service for faster isolated process startup. Requires Android 10+ and app restart."),
      ),
      secondary: const Icon(MdiIcons.rocketLaunch),
      value: appZygoteProcessEnabled,
      onChanged: (value) async {
        await ref
            .read(saveEngineSettingsControllerProvider.notifier)
            .save(
              (currentSettings) =>
                  currentSettings.copyWith.appZygoteProcessEnabled(value),
            );
        if (context.mounted) {
          await _showRestartDialog(context);
        }
      },
    );
  }
}

Future<void> _showRestartDialog(BuildContext context) async {
  final result = await showQuitBrowserDialog(context);
  if (result == true && context.mounted) {
    await exitApp(ProviderScope.containerOf(context));
  }
}
