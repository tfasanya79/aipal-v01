// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:html' as html;

void setWebPageTitleImpl(String title) {
  html.document.title = title;
}
