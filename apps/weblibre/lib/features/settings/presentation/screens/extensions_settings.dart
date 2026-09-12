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
import 'package:flutter_hooks/flutter_hooks.dart';
import 'package:flutter_material_design_icons/flutter_material_design_icons.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:weblibre/core/routing/routes.dart';
import 'package:weblibre/features/geckoview/features/browser/domain/services/browser_addon.dart';
import 'package:weblibre/features/settings/presentation/widgets/settings_detail.dart';
import 'package:weblibre/i18n/i18n.dart';

const List<SettingsSectionDefinition> extensionsSettingsSections = [
  SettingsSectionDefinition(
    title: 'Extensions',
    entries: [
      SettingsEntryDefinition(
        title: 'Manage Extensions',
        subtitle:
            'Browse installed, disabled, available, and unsupported extensions',
        keywords: ['addons', 'browser extensions'],
        child: _ManageExtensionsTile(),
      ),
      SettingsEntryDefinition(
        title: 'Custom Collection',
        subtitle: 'Use a custom Mozilla addon collection',
        keywords: ['addons'],
        child: _AddonCollectionTile(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Updates',
    entries: [
      SettingsEntryDefinition(
        title: 'Automatic updates',
        subtitle:
            'Automatically check for and install extension updates every 12 hours',
        keywords: ['addons'],
        child: _AutoUpdateTile(),
      ),
    ],
  ),
  SettingsSectionDefinition(
    title: 'Security',
    entries: [
      SettingsEntryDefinition(
        title: 'Allow unsigned extensions',
        subtitle: 'Unsigned extensions have not been verified by Mozilla',
        keywords: ['addons'],
        child: _AllowUnsignedExtensionsTile(),
      ),
    ],
  ),
];

class ExtensionsSettingsScreen extends StatelessWidget {
  const ExtensionsSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SettingsDetailScaffold(
      title: tr("Extensions"),
      subtitle: tr("Manage add-ons, update behavior, and extension security."),
      icon: MdiIcons.puzzleOutline,
      sections: extensionsSettingsSections,
    );
  }
}

class _ManageExtensionsTile extends StatelessWidget {
  const _ManageExtensionsTile();

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(
        MdiIcons.puzzleEdit,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      ),
      title: Text(tr("Manage Extensions")),
      subtitle: Text(
        tr("Browse installed, disabled, available, and unsupported extensions"),
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () async {
        await const AddonManagerRoute().push<void>(context);
      },
    );
  }
}

class _AddonCollectionTile extends StatelessWidget {
  const _AddonCollectionTile();

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(
        MdiIcons.folderMultiple,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      ),
      title: Text(tr("Custom Collection")),
      subtitle: Text(tr("Use a custom Mozilla addon collection")),
      trailing: const Icon(Icons.chevron_right),
      onTap: () async {
        await AddonCollectionRoute().push(context);
      },
    );
  }
}

class _AutoUpdateTile extends ConsumerWidget {
  const _AutoUpdateTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final autoUpdate = ref.watch(addonAutoUpdateProvider);

    return autoUpdate.when(
      data: (enabled) => SwitchListTile.adaptive(
        title: Text(tr("Automatic updates")),
        subtitle: Text(
          tr("Automatically check for and install extension updates every 12 hours"),
        ),
        secondary: const Icon(Icons.system_update_alt),
        value: enabled,
        onChanged: (value) async {
          await ref
              .read(addonAutoUpdateProvider.notifier)
              .setEnabled(enabled: value);
        },
      ),
      loading: () => SwitchListTile.adaptive(
        title: Text(tr("Automatic updates")),
        subtitle: Text(
          tr("Automatically check for and install extension updates every 12 hours"),
        ),
        secondary: Icon(Icons.system_update_alt),
        value: true,
        onChanged: null,
      ),
      error: (error, stack) => ListTile(
        leading: const Icon(Icons.error_outline),
        title: Text(tr("Automatic updates")),
        subtitle: Text(tr("Failed to load: {0}", [error])),
      ),
    );
  }
}

class _AllowUnsignedExtensionsTile extends ConsumerWidget {
  const _AllowUnsignedExtensionsTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final allowUnsigned = ref.watch(allowUnsignedExtensionsProvider);

    return allowUnsigned.when(
      data: (allowed) => Column(
        children: [
          SwitchListTile.adaptive(
            title: Text(tr("Allow unsigned extensions")),
            subtitle: Text(
              tr("Unsigned extensions have not been verified by Mozilla"),
            ),
            secondary: const Icon(Icons.extension_off),
            value: allowed,
            onChanged: (value) async {
              if (value) {
                final confirmed = await _showAllowUnsignedConfirmationDialog(
                  context,
                );
                if (confirmed != true) return;
              }
              await ref
                  .read(allowUnsignedExtensionsProvider.notifier)
                  .setAllowUnsigned(allow: value);
            },
          ),
          if (allowed)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(
                    context,
                  ).colorScheme.errorContainer.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Theme.of(context).colorScheme.error,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.warning_amber,
                      color: Theme.of(context).colorScheme.error,
                      size: 20,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        tr("Only install unsigned extensions from sources you trust. They may contain malicious code."),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.onErrorContainer,
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
      loading: () => SwitchListTile.adaptive(
        title: Text(tr("Allow unsigned extensions")),
        subtitle: Text(tr("Unsigned extensions have not been verified by Mozilla")),
        secondary: Icon(Icons.extension_off),
        value: false,
        onChanged: null,
      ),
      error: (error, stack) => ListTile(
        leading: const Icon(Icons.error_outline),
        title: Text(tr("Allow unsigned extensions")),
        subtitle: Text(tr("Failed to load: {0}", [error])),
      ),
    );
  }
}

Future<bool?> _showAllowUnsignedConfirmationDialog(BuildContext context) {
  return showDialog<bool>(
    context: context,
    builder: (context) => const _AllowUnsignedConfirmationDialog(),
  );
}

class _AllowUnsignedConfirmationDialog extends HookWidget {
  const _AllowUnsignedConfirmationDialog();

  static const _countdownSeconds = 15;

  @override
  Widget build(BuildContext context) {
    final remaining = useState(_countdownSeconds);

    useEffect(() {
      final timer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (remaining.value > 0) {
          remaining.value--;
        }
      });
      return timer.cancel;
    }, []);

    final theme = Theme.of(context);
    final canConfirm = remaining.value == 0;

    return AlertDialog(
      icon: Icon(
        Icons.warning_amber_rounded,
        color: theme.colorScheme.error,
        size: 40,
      ),
      title: Text(tr("Allow unsigned extensions?")),
      content: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text:
                  tr("Warning: This significantly weakens your browser's security.\n\n"),
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: theme.colorScheme.error,
              ),
            ),
            TextSpan(
              text:
                  tr("Unsigned extensions bypass Mozilla's safety review process. Malicious extensions can:\n\n• Read and modify everything you see on any website\n• Steal passwords, banking details, and personal data\n• Monitor your browsing activity silently\n• Install additional malware on your device\n\n"),
            ),
            TextSpan(
              text:
                  tr("Only enable this if you are a developer installing your own extension or absolutely trust the source."),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: Text(tr("Cancel")),
        ),
        FilledButton(
          onPressed: canConfirm ? () => Navigator.of(context).pop(true) : null,
          style: FilledButton.styleFrom(
            backgroundColor: theme.colorScheme.error,
            foregroundColor: theme.colorScheme.onError,
          ),
          child: Text(canConfirm ? tr("Allow") : tr("Allow ({0})", [remaining.value])),
        ),
      ],
    );
  }
}
