import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:emsalist_mobile/features/auth/data/apple_credential_provider.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AppleNonce', () {
    test('generateRaw returns requested length from safe charset', () {
      final String nonce = AppleNonce.generateRaw(32);
      expect(nonce.length, 32);
      expect(RegExp(r'^[A-Za-z0-9\-._]+$').hasMatch(nonce), isTrue);
    });

    test('generateRaw values are unique across calls', () {
      final Set<String> seen = <String>{};
      for (int i = 0; i < 50; i++) {
        seen.add(AppleNonce.generateRaw());
      }
      expect(seen.length, 50);
    });

    test('sha256Hex matches crypto SHA-256 of the raw nonce', () {
      const String raw = 'the-raw-nonce-value';
      final String expected = sha256.convert(utf8.encode(raw)).toString();
      expect(AppleNonce.sha256Hex(raw), expected);
    });
  });

  group('UnavailableAppleCredentialProvider', () {
    test('reports unavailable and throws on use', () async {
      const provider = UnavailableAppleCredentialProvider();
      expect(await provider.isAvailable(), isFalse);
      await expectLater(
        provider.getCredential(rawNonce: 'n'),
        throwsA(isA<AppleCredentialException>()),
      );
    });
  });
}
