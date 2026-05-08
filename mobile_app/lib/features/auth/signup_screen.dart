import 'package:flutter/material.dart';

class SignupScreen extends StatelessWidget {
  const SignupScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const _AuthScaffold(
      title: 'Create your account',
      subtitle: 'Join verarel.com and start matching with confidence.',
      child: _SignupForm(),
    );
  }
}

class _AuthScaffold extends StatelessWidget {
  const _AuthScaffold({
    required this.title,
    required this.subtitle,
    required this.child,
  });

  final String title;
  final String subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(title, style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 8),
              Text(subtitle),
              const SizedBox(height: 24),
              child,
            ],
          ),
        ),
      ),
    );
  }
}

class _SignupForm extends StatelessWidget {
  const _SignupForm();

  @override
  Widget build(BuildContext context) {
    return const _PlaceholderForm(actionLabel: 'Create account');
  }
}

class _PlaceholderForm extends StatelessWidget {
  const _PlaceholderForm({required this.actionLabel});

  final String actionLabel;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        const TextField(decoration: InputDecoration(labelText: 'Email')),
        const SizedBox(height: 12),
        const TextField(decoration: InputDecoration(labelText: 'Password'), obscureText: true),
        const SizedBox(height: 12),
        const TextField(decoration: InputDecoration(labelText: 'Display name')),
        const SizedBox(height: 20),
        FilledButton(
          onPressed: () {},
          child: Text(actionLabel),
        ),
      ],
    );
  }
}
