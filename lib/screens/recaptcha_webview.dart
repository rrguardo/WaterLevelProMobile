import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
// ignore: depend_on_referenced_packages
import 'package:webview_flutter_android/webview_flutter_android.dart';
import '../constants.dart';

class RecaptchaWebView extends StatefulWidget {
  const RecaptchaWebView({super.key});

  @override
  State<RecaptchaWebView> createState() => _RecaptchaWebViewState();
}

class _RecaptchaWebViewState extends State<RecaptchaWebView> {
  late final WebViewController _controller;

  @override
  void initState() {
    super.initState();
    final htmlContent = '''
      <!DOCTYPE html>
      <html>
        <head>
          <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0">
          <title>reCAPTCHA</title>
          <style>
            body {
              display: flex;
              flex-direction: column;
              justify-content: center;
              align-items: center;
              height: 100vh;
              margin: 0;
              background-color: #ffffff;
              font-family: sans-serif;
            }
          </style>
          <script type="text/javascript">
            function captchaCallback(response) {
              if (typeof Captcha !== 'undefined') {
                Captcha.postMessage(response);
              }
            }
            var onloadCallback = function() {
              grecaptcha.render('captcha_container', {
                'sitekey' : '$recaptchaPublicKey',
                'callback' : captchaCallback
              });
            };
          </script>
          <script src="https://www.google.com/recaptcha/api.js?onload=onloadCallback&render=explicit" async defer></script>
        </head>
        <body>
          <div style="margin-bottom: 20px; color: #666;">Verificando seguridad...</div>
          <div id="captcha_container"></div>
        </body>
      </html>
    ''';

    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFFFFFFFF))
      ..setUserAgent("Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36")
      ..addJavaScriptChannel('Captcha', onMessageReceived: (JavaScriptMessage msg) {
        Navigator.pop(context, msg.message);
      });

    if (_controller.platform is AndroidWebViewController) {
      AndroidWebViewController.enableDebugging(true);
      (_controller.platform as AndroidWebViewController).setMediaPlaybackRequiresUserGesture(false);
    }

    _controller.loadHtmlString(htmlContent, baseUrl: "https://waterlevel.pro");
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.close, color: Colors.black),
          onPressed: () => Navigator.pop(context, null),
        ),
      ),
      body: WebViewWidget(controller: _controller),
    );
  }
}
