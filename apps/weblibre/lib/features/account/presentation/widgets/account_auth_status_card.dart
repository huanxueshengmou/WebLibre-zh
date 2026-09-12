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
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:weblibre/features/account/data/account_adoption.dart';
import 'package:weblibre/features/account/data/account_adoption_provider.dart';
import 'package:weblibre/features/account/data/models/account_auth_state.dart';
import 'package:weblibre/features/account/domain/repositories/account_auth.dart';
import 'package:weblibre/i18n/i18n.dart';

/// Body of the "Account" settings entry. Renders the auth state machine:
/// signed-out CTA, signing-in spinner with cancel, signed-in identity with
/// sign-out + sync-key reset, or an error tile with retry.
class AccountAuthStatusCard extends ConsumerWidget {
  const AccountAuthStatusCard({super.key, required this.authState});

  final AccountAuthState authState;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return switch (authState.status) {
      AccountAuthStatus.signedOut => _SignedOutSection(authState: authState),
      AccountAuthStatus.signingIn => const _SigningInTile(),
      AccountAuthStatus.signedIn => _SignedInTile(authState: authState),
      AccountAuthStatus.error => _ErrorTile(authState: authState),
    };
  }
}

/// Signed out — but possibly only because the upgrade could not tell which
/// profile the existing session belonged to.
///
/// Qualifying secure-storage keys by profile fixed a real isolation defect (one
/// session was shared by every profile), and the cost was that the pre-existing
/// record has no owner. Nothing on the device records which profile it was for.
/// Rather than guess, or discard it and call that a migration, the session is
/// offered back here by name — the user is the only party who knows.
class _SignedOutSection extends ConsumerWidget {
  const _SignedOutSection({required this.authState});

  final AccountAuthState authState;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unclaimed = ref.watch(unclaimedAccountRecordProvider).value;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (unclaimed != null) _AdoptAccountTile(record: unclaimed),
        _SignedOutTile(knownAccount: authState.email ?? authState.displayName),
      ],
    );
  }
}

class _AdoptAccountTile extends ConsumerWidget {
  const _AdoptAccountTile({required this.record});

  final UnclaimedAccountRecord record;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    // Watched, not read: the controller is what says whether the answer is
    // still being carried out, and both buttons stay inert-looking without it.
    final adoption = ref.watch(accountAdoptionProvider);
    final busy = adoption.isLoading;

    return Card(
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      color: theme.colorScheme.secondaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.person_search_outlined,
                  color: theme.colorScheme.onSecondaryContainer,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    record.isUsable
                        ? tr("An older sign-in is still on this device")
                        : tr("An older sign-in cannot be read"),
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: theme.colorScheme.onSecondaryContainer,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              record.isUsable
                  // Says where it came from, because the moment this card is
                  // most likely to be seen is straight after a restore — and it
                  // has nothing to do with the archive. A restore into a new
                  // profile deliberately leaves the archive's account behind, so
                  // reading this as "your backed-up account" would be exactly
                  // wrong.
                  ? tr("WebLibre kept a sign-in for {0} from before profiles had separate accounts. It is not from a backup, and nothing on this device records which profile it belonged to — so it will not be guessed at.", [record.label])
                  : 'WebLibre kept a sign-in from before profiles had separate '
                        'accounts, but the saved data is damaged and cannot be '
                        'used to sign in. Signing in again is the only way '
                        'back; removing it clears this message.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSecondaryContainer,
              ),
            ),
            if (adoption.hasError) ...[
              const SizedBox(height: 12),
              Text(
                'That did not work. Check your connection and try again.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: busy
                      ? null
                      : () async {
                          final confirmed = await _confirmDiscard(
                            context,
                            record,
                          );
                          if (confirmed != true) return;
                          // The dialog is an async gap, and this `ref` belongs
                          // to the widget: using it after the settings screen
                          // has gone throws. The controller itself is keepAlive,
                          // so a discard already under way is unaffected.
                          if (!context.mounted) return;
                          await ref
                              .read(accountAdoptionProvider.notifier)
                              .discard(record);
                        },
                  child: Text(record.isUsable ? tr("Not mine") : tr("Remove it")),
                ),
                if (record.isUsable) ...[
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: busy
                        ? null
                        : () async {
                            await ref
                                .read(accountAdoptionProvider.notifier)
                                .adopt(record);
                          },
                    child: busy
                        ? const SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(tr("Use it here")),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Confirmed, because it is the only irreversible half of the choice.
///
/// "Use it here" can be undone by signing out; discarding destroys the only copy
/// of a session that may belong to another profile the user has not opened yet.
Future<bool?> _confirmDiscard(
  BuildContext context,
  UnclaimedAccountRecord record,
) => showDialog<bool>(
  context: context,
  builder: (context) => AlertDialog(
    title: Text(tr("Forget this sign-in?")),
    content: Text(
      tr("The saved session for {0} is deleted from this device. If it belonged to another profile, you have to sign in again there.", [record.label]),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context, false),
        child: Text(tr("Cancel")),
      ),
      TextButton(
        onPressed: () => Navigator.pop(context, true),
        child: Text(tr("Forget it")),
      ),
    ],
  ),
);

class _SignedOutTile extends ConsumerWidget {
  const _SignedOutTile({this.knownAccount});

  /// The account this profile was last signed in as, when the stored record
  /// still says. Present after a session expired or was revoked — including the
  /// common case of restoring a backup old enough that its refresh token no
  /// longer works — where "Sign in" alone leaves the user guessing which account
  /// the restore was supposed to bring back.
  final String? knownAccount;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListTile(
      leading: const Icon(Icons.login),
      title: Text(
        knownAccount == null
            ? tr("Sign in to WebLibre Account")
            : tr("Sign in again as {0}", [knownAccount]),
      ),
      subtitle: Text(
        knownAccount == null
            ? tr("Sync your settings across devices")
            : tr("This profile's saved sign-in expired. Your sync key is kept."),
      ),
      contentPadding: const EdgeInsets.symmetric(
        vertical: 8.0,
        horizontal: 16.0,
      ),
      trailing: const Icon(Icons.chevron_right),
      onTap: () async {
        await ref.read(accountAuthRepositoryProvider.notifier).startSignIn();
      },
    );
  }
}

class _SigningInTile extends ConsumerWidget {
  const _SigningInTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.all(24.0),
      child: Column(
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(tr("Signing in...")),
          const SizedBox(height: 8),
          Text(
            tr("Complete sign-in in WebLibre"),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 16),
          TextButton(
            onPressed: () async {
              await ref
                  .read(accountAuthRepositoryProvider.notifier)
                  .cancelSignIn();
            },
            child: Text(tr("Cancel")),
          ),
        ],
      ),
    );
  }
}

class _SignedInTile extends ConsumerWidget {
  const _SignedInTile({required this.authState});

  final AccountAuthState authState;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      children: [
        ListTile(
          leading: const Icon(Icons.account_circle),
          title: Text(authState.displayName ?? authState.email ?? tr("Signed in")),
          subtitle:
              authState.email != null &&
                  authState.email != authState.displayName
              ? Text(authState.email!)
              : null,
          trailing: IconButton(
            icon: const Icon(Icons.logout),
            tooltip: tr("Sign Out"),
            onPressed: () async {
              final confirmed = await _showSignOutConfirmation(context);
              if (confirmed == true) {
                await ref
                    .read(accountAuthRepositoryProvider.notifier)
                    .signOut();
              }
            },
          ),
          contentPadding: const EdgeInsets.symmetric(
            vertical: 8.0,
            horizontal: 16.0,
          ),
        ),
        if (authState.hasSyncKey) ...[
          const Divider(height: 1),
          const _ResetSyncKeyTile(),
        ],
      ],
    );
  }

  static Future<bool?> _showSignOutConfirmation(BuildContext context) {
    return showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text(tr("Sign out?")),
          content: Text(
            tr("Are you sure you want to sign out of your WebLibre Account?"),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(tr("Cancel")),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(tr("Sign Out")),
            ),
          ],
        );
      },
    );
  }
}

class _ErrorTile extends ConsumerWidget {
  const _ErrorTile({required this.authState});

  final AccountAuthState authState;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(16.0),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                // A session that expired under a known account is a different
                // situation from a sign-in that failed, and saying "Sign-in
                // failed" over a restored profile reads as though the restore
                // itself went wrong.
                authState.email == null
                    ? tr("Sign-in failed")
                    : 'Sign in again as ${authState.email}',
                style: TextStyle(
                  color: colorScheme.onErrorContainer,
                  fontWeight: FontWeight.bold,
                ),
              ),
              if (authState.lastError != null) ...[
                const SizedBox(height: 8),
                Text(
                  authState.lastError!,
                  style: TextStyle(color: colorScheme.onErrorContainer),
                ),
              ],
              const SizedBox(height: 16),
              FilledButton.tonal(
                onPressed: () async {
                  await ref
                      .read(accountAuthRepositoryProvider.notifier)
                      .startSignIn();
                },
                child: Text(tr("Try Again")),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ResetSyncKeyTile extends ConsumerWidget {
  const _ResetSyncKeyTile();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListTile(
      leading: const Icon(Icons.key_off_outlined),
      title: Text(tr("Reset Sync Key")),
      subtitle: Text(
        tr("Re-enter your password if you mistyped it or changed it"),
      ),
      onTap: () async {
        final confirmed = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(tr("Reset Sync Key")),
            content: Text(
              tr("You will need to re-enter your account password. If your password changed, existing snapshots encrypted with the old password will no longer be decryptable."),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: Text(tr("Cancel")),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: Text(tr("Reset")),
              ),
            ],
          ),
        );
        if (confirmed == true) {
          await ref.read(accountAuthRepositoryProvider.notifier).clearSyncKey();
        }
      },
    );
  }
}
