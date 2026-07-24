# flutter_local_notifications + Gson TypeToken (R8 release builds)
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.google.gson.reflect.TypeToken { *; }
-keep class * extends com.google.gson.reflect.TypeToken
-keepclassmembers class * extends com.google.gson.reflect.TypeToken {
    <init>();
}
