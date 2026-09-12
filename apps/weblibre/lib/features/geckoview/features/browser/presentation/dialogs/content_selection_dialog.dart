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
import 'package:weblibre/features/geckoview/features/tabs/data/database/definitions.drift.dart';
import 'package:weblibre/i18n/i18n.dart';

/// Dialog to select between extracted or full content for sharing.
/// Shows options for extracted (reader-optimized) vs full (complete) content.
Future<void> showContentSelectionDialog(
  BuildContext context, {
  required Widget title,
  required TabData tabData,
  required Future<void> Function(String content, String? fileName)
  shareMarkdownAction,
}) async {
  await showDialog(
    context: context,
    builder: (context) => SimpleDialog(
      title: title,
      children: [
        ListTile(
          title: Text(tr("Extracted Content")),
          subtitle: Text(
            tr("Reader-optimized content without navigation and ads"),
          ),
          onTap: () async {
            Navigator.of(context).pop();
            await shareMarkdownAction(
              tabData.extractedContentMarkdown!,
              tabData.title ?? tabData.url?.authority,
            );
          },
        ),
        ListTile(
          title: Text(tr("Full Content")),
          subtitle: Text(
            tr("Complete page including all elements and structure"),
          ),
          onTap: () async {
            Navigator.of(context).pop();
            await shareMarkdownAction(
              tabData.fullContentMarkdown!,
              tabData.title ?? tabData.url?.authority,
            );
          },
        ),
      ],
    ),
  );
}
