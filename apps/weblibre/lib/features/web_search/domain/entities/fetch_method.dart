import 'package:flutter/material.dart';
import 'package:weblibre/i18n/i18n.dart';

/// Capture pipeline selector. Each choice maps to a (method, variant) pair
/// understood by the search backend's capture clients.
enum FetchMethodChoice {
  /// Trafilatura — extracted reader-mode text + metadata. Not a "capture"
  /// per se; goes through the `fetchPage` command.
  trafilatura(method: null, variant: null),

  /// SingleFile — self-contained HTML archive.
  singlefileHtml(method: 'singlefile', variant: 'balanced'),

  /// shot-scraper — PDF rendering.
  shotScraperPdf(method: 'shot-scraper', variant: 'pdf'),

  /// shot-scraper — PNG screenshot.
  shotScraperPng(method: 'shot-scraper', variant: 'png');

  const FetchMethodChoice({required this.method, required this.variant});

  final String? method;
  final String? variant;

  static FetchMethodChoice? forCapture({
    required String method,
    required String variant,
  }) {
    for (final choice in FetchMethodChoice.values) {
      if (choice.method == method && choice.variant == variant) {
        return choice;
      }
    }
    return null;
  }

  String get title => switch (this) {
    FetchMethodChoice.trafilatura => tr("Extracted Preview"),
    FetchMethodChoice.singlefileHtml => tr("Full Page Capture"),
    FetchMethodChoice.shotScraperPdf => tr("PDF Snapshot"),
    FetchMethodChoice.shotScraperPng => tr("Image Snapshot"),
  };

  String get shortLabel => switch (this) {
    FetchMethodChoice.trafilatura => 'Preview',
    FetchMethodChoice.singlefileHtml => 'Archive',
    FetchMethodChoice.shotScraperPdf => 'PDF',
    FetchMethodChoice.shotScraperPng => 'Image',
  };

  String get subtitle => switch (this) {
    FetchMethodChoice.trafilatura =>
      tr("Reader-optimized text and metadata for the in-app preview"),
    FetchMethodChoice.singlefileHtml =>
      tr("Archive the full page with layout and assets for later use"),
    FetchMethodChoice.shotScraperPdf =>
      tr("Render the page to a PDF for offline reading and sharing"),
    FetchMethodChoice.shotScraperPng =>
      tr("Capture a full-page PNG screenshot of the rendered page"),
  };

  IconData get icon => switch (this) {
    FetchMethodChoice.trafilatura => Icons.description_outlined,
    FetchMethodChoice.singlefileHtml => Icons.archive_outlined,
    FetchMethodChoice.shotScraperPdf => Icons.picture_as_pdf_outlined,
    FetchMethodChoice.shotScraperPng => Icons.image_outlined,
  };
}
