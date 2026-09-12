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
import 'package:flutter_hooks/flutter_hooks.dart';
import 'package:flutter_material_design_icons/flutter_material_design_icons.dart';
import 'package:flutter_mozilla_components/flutter_mozilla_components.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:weblibre/extensions/uri.dart';
import 'package:weblibre/features/settings/presentation/controllers/save_settings.dart';
import 'package:weblibre/features/user/data/models/engine_settings.dart';
import 'package:weblibre/features/user/domain/repositories/engine_settings.dart';
import 'package:weblibre/utils/form_validators.dart';
import 'package:weblibre/i18n/i18n.dart';

class DohSettingsContent extends HookConsumerWidget {
  const DohSettingsContent({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    final dohSettings = ref.watch(
      engineSettingsWithDefaultsProvider.select((value) => value.dohSettings),
    );
    // Already includes a resolver that predates saved resolvers — the model
    // adopts it out of `dohProviderUrl` on deserialization.
    final resolvers = ref.watch(
      engineSettingsWithDefaultsProvider.select(
        (value) => value.customDohProviders,
      ),
    );

    Future<void> save(UpdateEngineSettingsFunc updateSettings) {
      return ref
          .read(saveEngineSettingsControllerProvider.notifier)
          .save(updateSettings);
    }

    final selectedUrl = dohSettings.dohProviderUrl;

    return Column(
      children: [
        ListTile(
          leading: Icon(MdiIcons.dns),
          title: Text(tr("Protection Level")),
          subtitle: Text(
            tr("Domain Name System (DNS) over HTTPS sends your request for a domain name through an encrypted connection, providing a secure DNS and making it harder for others to see which web site you’re about to access."),
          ),
        ),
        RadioGroup(
          groupValue: dohSettings.dohSettingsMode,
          onChanged: (value) async {
            if (value != null) {
              await save(
                (currentSettings) =>
                    currentSettings.copyWith.dohSettingsMode(value),
              );
            }
          },
          child: Column(
            children: [
              RadioListTile.adaptive(
                value: DohSettingsMode.geckoDefault,
                title: Text(tr("Default Protection")),
                subtitle: Text(tr("DoH used only when default DNS fails")),
              ),
              RadioListTile.adaptive(
                value: DohSettingsMode.increased,
                title: Text(tr("Increased Protection")),
                subtitle: Text(tr("DoH preferred, default DNS as fallback")),
              ),
              RadioListTile.adaptive(
                value: DohSettingsMode.max,
                title: Text(tr("Max Protection")),
                subtitle: Text(tr("DoH only, no fallback")),
              ),
              RadioListTile.adaptive(
                value: DohSettingsMode.off,
                title: Text(tr("Off")),
                subtitle: Text(tr("Use your default DNS resolver")),
              ),
            ],
          ),
        ),
        ListTile(
          leading: Icon(MdiIcons.routerNetwork),
          title: Text(tr("DoH Provider")),
        ),
        RadioGroup(
          groupValue: selectedUrl,
          onChanged: (value) async {
            if (value != null) {
              await save(
                (currentSettings) =>
                    currentSettings.copyWith.dohProviderUrl(value),
              );
            }
          },
          child: Column(
            children: [
              ...BuiltInDohProviders.values.map(
                (provider) => RadioListTile.adaptive(
                  value: provider.url,
                  title: Text(provider.name),
                  subtitle: Text(provider.url.uriDisplayString),
                ),
              ),
              if (resolvers.isNotEmpty)
                ListTile(
                  dense: true,
                  title: Text(
                    tr("Your resolvers"),
                    style: theme.textTheme.labelLarge?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ...resolvers.map(
                (provider) => RadioListTile.adaptive(
                  value: provider.url,
                  title: Text(provider.displayName),
                  subtitle: Text(provider.url.uriDisplayString),
                  secondary: _ResolverActions(
                    onEdit: () async {
                      final result = await _promptForResolver(
                        context,
                        existing: resolvers,
                        initial: provider,
                      );
                      if (result == null) {
                        return;
                      }

                      await save((currentSettings) {
                        final updated = [...currentSettings.customDohProviders];
                        final index = updated.indexWhere(
                          (entry) => entry.url == provider.url,
                        );
                        if (index >= 0) {
                          updated[index] = result;
                        } else {
                          updated.add(result);
                        }

                        final settings = currentSettings.copyWith
                            .customDohProviders(updated);

                        return currentSettings.dohProviderUrl == provider.url
                            ? settings.copyWith.dohProviderUrl(result.url)
                            : settings;
                      });
                    },
                    onDelete: () async {
                      await save((currentSettings) {
                        final updated = [...currentSettings.customDohProviders]
                          ..removeWhere((entry) => entry.url == provider.url);

                        final settings = currentSettings.copyWith
                            .customDohProviders(updated);

                        // Never leave the engine pointed at a resolver that no
                        // longer exists — under max protection there is no
                        // fallback, so name resolution would stop entirely.
                        return currentSettings.dohProviderUrl == provider.url
                            ? settings.copyWith.dohProviderUrl(
                                currentSettings.dohDefaultProviderUrl,
                              )
                            : settings;
                      });
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: SizedBox(
            width: double.infinity,
            child: FilledButton.tonalIcon(
              icon: const Icon(Icons.add),
              label: Text(tr("Add custom resolver")),
              onPressed: resolvers.length >= kMaxCustomDohProviders
                  ? null
                  : () async {
                      final result = await _promptForResolver(
                        context,
                        existing: resolvers,
                      );
                      if (result == null) {
                        return;
                      }

                      await save(
                        (currentSettings) => currentSettings.copyWith
                            .customDohProviders([
                              ...currentSettings.customDohProviders,
                              result,
                            ])
                            .copyWith
                            .dohProviderUrl(result.url),
                      );
                    },
            ),
          ),
        ),
      ],
    );
  }
}

class _ResolverActions extends StatelessWidget {
  final VoidCallback onEdit;
  final VoidCallback onDelete;

  const _ResolverActions({required this.onEdit, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          icon: const Icon(Icons.edit_outlined),
          color: colorScheme.onSurfaceVariant,
          tooltip: tr("Edit"),
          visualDensity: VisualDensity.compact,
          onPressed: onEdit,
        ),
        IconButton(
          icon: const Icon(Icons.delete_outline),
          color: colorScheme.onSurfaceVariant,
          tooltip: tr("Remove"),
          visualDensity: VisualDensity.compact,
          onPressed: onDelete,
        ),
      ],
    );
  }
}

Future<CustomDohProvider?> _promptForResolver(
  BuildContext context, {
  required List<CustomDohProvider> existing,
  CustomDohProvider? initial,
}) {
  return showDialog<CustomDohProvider>(
    context: context,
    builder: (context) =>
        _CustomResolverDialog(existing: existing, initial: initial),
  );
}

class _CustomResolverDialog extends HookWidget {
  final List<CustomDohProvider> existing;
  final CustomDohProvider? initial;

  const _CustomResolverDialog({required this.existing, this.initial});

  @override
  Widget build(BuildContext context) {
    final isEdit = initial != null;
    final formKey = useMemoized(() => GlobalKey<FormState>());
    final urlController = useTextEditingController(text: initial?.url ?? '');
    final nameController = useTextEditingController(text: initial?.name ?? '');

    return AlertDialog(
      title: Text(isEdit ? tr("Edit custom resolver") : tr("Add custom resolver")),
      content: Form(
        key: formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              controller: urlController,
              autofocus: !isEdit,
              keyboardType: TextInputType.url,
              decoration: InputDecoration(
                labelText: tr("Resolver URL"),
                hintText: 'https://example.com/dns-query',
              ),
              validator: (value) {
                final trimmed = value?.trim() ?? '';

                final urlError = validateUrl(
                  trimmed,
                  onlyHttpProtocol: true,
                  eagerParsing: false,
                );
                if (urlError != null) {
                  return urlError;
                }

                if (BuiltInDohProviders.isBuiltin(trimmed)) {
                  return 'Already available as a built-in provider';
                }

                final clash = existing.any(
                  (entry) => entry.url == trimmed && entry.url != initial?.url,
                );
                if (clash) {
                  return 'Already added';
                }

                return null;
              },
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: nameController,
              autofocus: isEdit,
              maxLength: 40,
              decoration: InputDecoration(
                labelText: tr("Name (optional)"),
                hintText: tr("e.g. dnsforge (adblock)"),
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(tr("Cancel")),
        ),
        FilledButton(
          onPressed: () {
            if (formKey.currentState?.validate() == true) {
              final name = nameController.text.trim();

              Navigator.of(context).pop(
                CustomDohProvider(
                  url: urlController.text.trim(),
                  name: name.isEmpty ? null : name,
                ),
              );
            }
          },
          child: Text(isEdit ? tr("Save") : tr("Save and use")),
        ),
      ],
    );
  }
}
