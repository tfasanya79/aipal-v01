// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:convert';
import 'dart:html' as html;

Future<String?> saveJsonFile(String filename, String content) async {
  final bytes = utf8.encode(content);
  final blob = html.Blob([bytes], 'application/json');
  final url = html.Url.createObjectUrlFromBlob(blob);
  final anchor = html.AnchorElement(href: url)..download = filename;
  anchor.click();
  html.Url.revokeObjectUrl(url);
  return filename;
}
