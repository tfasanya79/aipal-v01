export 'memory_export_stub.dart'
    if (dart.library.html) 'memory_export_web.dart'
    if (dart.library.io) 'memory_export_io.dart';
