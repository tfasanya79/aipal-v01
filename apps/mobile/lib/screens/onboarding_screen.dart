import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/app_state.dart';
import '../widgets/aipal_logo.dart';
import '../services/notification_service.dart';
import 'home_shell.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, this.continueProfile = false});

  final bool continueProfile;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _email = TextEditingController();
  final _wakeName = TextEditingController();
  final _about = TextEditingController();

  int _step = 0;
  String? _error;
  String? _validatedEmail;

  @override
  void initState() {
    super.initState();
    if (widget.continueProfile) _step = 1;
  }

  bool _isValidEmail(String email) {
    final trimmed = email.trim();
    if (trimmed.isEmpty) return false;
    final at = trimmed.indexOf('@');
    return at > 0 && trimmed.contains('.') && at < trimmed.length - 1;
  }

  void _onContinueFromEmail() {
    final email = _email.text.trim();
    if (!_isValidEmail(email)) {
      setState(() => _error = 'Enter a valid email address');
      return;
    }

    setState(() {
      _error = null;
      _validatedEmail = email;
      _step = 1;
    });
  }

  Future<void> _finish() async {
    final state = context.read<AppState>();

    try {
      if (!widget.continueProfile) {
        final email = _validatedEmail ?? _email.text.trim();

        if (!_isValidEmail(email)) {
          setState(() => _error = 'Enter a valid email address');
          return;
        }

        await state.login(email);
      }

      await state.updateProfile({
        'wake_name': _wakeName.text.trim().isEmpty
            ? 'friend'
            : _wakeName.text.trim(),
        'display_name': _wakeName.text.trim(),
        'about_me': _about.text.trim(),
        'morning_brief_at': '08:00',
        'evening_recap_at': '20:00',
      });

      try {
        await NotificationService.instance.scheduleMorningBrief(
          hour: 8,
          minute: 0,
        );
        await NotificationService.instance.scheduleEveningRecap(
          hour: 20,
          minute: 0,
        );
      } catch (_) {
        // Notifications optional — must not block onboarding (R8 / sideload).
      }

      if (!mounted) return;

      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const HomeShell()));
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final isEmailStep = _step == 0 && !widget.continueProfile;

    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F5),
      body: Stack(
        children: [
          const _SoftBackground(),

          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
                  child: _GlassCard(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (isEmailStep) ...[
                          const _BrandHeader(),
                          const SizedBox(height: 48),
                        ] else ...[
                          const _ProgressIndicatorBar(),
                          const SizedBox(height: 36),
                        ],

                        Text(
                          isEmailStep ? 'Welcome' : 'Tell me about you',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontFamily: 'Manrope',
                            fontSize: 32,
                            height: 1.25,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.4,
                            color: Color(0xFF1B1C1A),
                          ),
                        ),

                        const SizedBox(height: 10),

                        Text(
                          isEmailStep
                              ? 'Not a substitute for emergency or professional care.'
                              : 'Help me tailor my responses to your specific world and rhythm.',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontSize: 14,
                            height: 1.45,
                            fontWeight: FontWeight.w500,
                            color: Color(0xFF4B444D),
                          ),
                        ),

                        const SizedBox(height: 34),

                        if (isEmailStep) ...[
                          _PremiumTextField(
                            controller: _email,
                            hintText: 'Email for magic link',
                            keyboardType: TextInputType.emailAddress,
                            onChanged: (_) {
                              if (_error != null) {
                                setState(() => _error = null);
                              }
                            },
                          ),
                        ] else ...[
                          _PremiumLabeledField(
                            label: 'What should I call you?',
                            child: _PremiumTextField(
                              controller: _wakeName,
                              hintText: 'Your name or nickname',
                            ),
                          ),
                          const SizedBox(height: 18),
                          _PremiumLabeledField(
                            label: 'A bit about yourself',
                            trailing: 'Optional',
                            child: _PremiumTextField(
                              controller: _about,
                              hintText:
                                  "E.g. I'm a morning person who loves focus work...",
                              maxLines: 4,
                            ),
                          ),
                        ],

                        if (_error != null) ...[
                          const SizedBox(height: 14),
                          Text(
                            _error!,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Color(0xFFBA1A1A),
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                            ),
                          ),
                        ],

                        const SizedBox(height: 28),

                        _GradientButton(
                          label: isEmailStep ? 'Continue' : 'Start with AiPal',
                          onPressed: () {
                            if (isEmailStep) {
                              _onContinueFromEmail();
                            } else {
                              _finish();
                            }
                          },
                        ),

                        if (isEmailStep) ...[
                          const SizedBox(height: 32),
                          const Divider(color: Color(0x1A7D747E), height: 1),
                          const SizedBox(height: 20),
                          const _PrivacyChip(),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),

          const Positioned(
            left: 0,
            right: 0,
            bottom: 24,
            child: _OnboardingFooter(),
          ),
        ],
      ),
    );
  }
}

class _SoftBackground extends StatelessWidget {
  const _SoftBackground();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned(
          top: 120,
          left: -160,
          child: _BlurBlob(
            color: const Color(0xFFB7ECEC).withValues(alpha: 0.45),
          ),
        ),
        Positioned(
          bottom: 90,
          right: -160,
          child: _BlurBlob(
            color: const Color(0xFFDFB9F2).withValues(alpha: 0.35),
          ),
        ),
      ],
    );
  }
}

class _BlurBlob extends StatelessWidget {
  const _BlurBlob({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 360,
      height: 360,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [BoxShadow(color: color, blurRadius: 120, spreadRadius: 40)],
      ),
    );
  }
}

class _GlassCard extends StatelessWidget {
  const _GlassCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(40),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.42),
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: Colors.white.withValues(alpha: 0.72)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1A1F2C).withValues(alpha: 0.04),
            blurRadius: 60,
            offset: const Offset(0, 30),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _BrandHeader extends StatelessWidget {
  const _BrandHeader();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [_FloatingOrb(), SizedBox(height: 16), AiPalLogo(size: 36)],
    );
  }
}

class _FloatingOrb extends StatelessWidget {
  const _FloatingOrb();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 64,
      height: 64,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFFFFC815), Color(0xFF003B2B)],
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFFFC815).withValues(alpha: 0.24),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: const Icon(
        Icons.auto_awesome_rounded,
        color: Colors.white,
        size: 32,
      ),
    );
  }
}

class _ProgressIndicatorBar extends StatelessWidget {
  const _ProgressIndicatorBar();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _bar(32, const Color(0xFFE3E2DF)),
        const SizedBox(width: 8),
        _bar(48, const Color(0xFFFFC815)),
        const SizedBox(width: 8),
        _bar(32, const Color(0xFFE3E2DF)),
      ],
    );
  }

  Widget _bar(double width, Color color) {
    return Container(
      width: width,
      height: 4,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
      ),
    );
  }
}

class _PremiumLabeledField extends StatelessWidget {
  const _PremiumLabeledField({
    required this.label,
    required this.child,
    this.trailing,
  });

  final String label;
  final String? trailing;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Row(
            children: [
              Text(
                label,
                style: const TextStyle(
                  fontSize: 14,
                  height: 1.4,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF1B1C1A),
                ),
              ),
              const Spacer(),
              if (trailing != null)
                Text(
                  trailing!,
                  style: const TextStyle(
                    fontSize: 13,
                    color: Color(0xFF6D6655),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        child,
      ],
    );
  }
}

class _PremiumTextField extends StatelessWidget {
  const _PremiumTextField({
    required this.controller,
    required this.hintText,
    this.keyboardType,
    this.maxLines = 1,
    this.onChanged,
  });

  final TextEditingController controller;
  final String hintText;
  final TextInputType? keyboardType;
  final int maxLines;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) {
    final isMultiLine = maxLines > 1;

    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      maxLines: maxLines,
      onChanged: onChanged,
      style: const TextStyle(
        fontSize: 16,
        color: Color(0xFF1B1C1A),
        fontWeight: FontWeight.w500,
      ),
      decoration: InputDecoration(
        hintText: hintText,
        hintStyle: const TextStyle(
          color: Color(0xFF9A929B),
          fontWeight: FontWeight.w400,
        ),
        filled: true,
        fillColor: Colors.white,
        contentPadding: EdgeInsets.symmetric(
          horizontal: 24,
          vertical: isMultiLine ? 20 : 0,
        ),
        constraints: isMultiLine ? null : const BoxConstraints(minHeight: 56),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(isMultiLine ? 32 : 999),
          borderSide: const BorderSide(color: Color(0xFFC6BEC9), width: 1.4),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(isMultiLine ? 32 : 999),
          borderSide: const BorderSide(color: Color(0xFFC6BEC9), width: 1.4),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(isMultiLine ? 32 : 999),
          borderSide: const BorderSide(color: Color(0xFFFFC815), width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(isMultiLine ? 32 : 999),
          borderSide: const BorderSide(color: Color(0xFFBA1A1A), width: 2),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(isMultiLine ? 32 : 999),
          borderSide: const BorderSide(color: Color(0xFFBA1A1A), width: 2),
        ),
      ),
    );
  }
}

class _GradientButton extends StatelessWidget {
  const _GradientButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        borderRadius: BorderRadius.circular(999),
        onTap: onPressed,
        child: Ink(
          height: 56,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            gradient: const LinearGradient(
              begin: Alignment.centerLeft,
              end: Alignment.centerRight,
              colors: [Color(0xFFFFC815), Color(0xFF003B2B)],
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFFFFC815).withValues(alpha: 0.18),
                blurRadius: 22,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  height: 1.4,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.1,
                ),
              ),
              const SizedBox(width: 8),
              const Icon(
                Icons.arrow_forward_rounded,
                color: Colors.white,
                size: 18,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PrivacyChip extends StatelessWidget {
  const _PrivacyChip();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.52),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: const Color(0xFFFFC815).withValues(alpha: 0.1),
        ),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.verified_user_outlined,
            size: 15,
            color: Color(0xFFFFC815),
          ),
          SizedBox(width: 6),
          Text(
            'Privacy by Design',
            style: TextStyle(
              fontSize: 12,
              height: 1.4,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
              color: Color(0xFF424655),
            ),
          ),
        ],
      ),
    );
  }
}

class _OnboardingFooter extends StatelessWidget {
  const _OnboardingFooter();

  @override
  Widget build(BuildContext context) {
    return const Text(
      '© 2024 AiPal. Serene Intelligence.',
      textAlign: TextAlign.center,
      style: TextStyle(
        fontSize: 12,
        height: 1.4,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.4,
        color: Color(0x99424655),
      ),
    );
  }
}
