import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../providers/app_state.dart';
import 'home_shell.dart';
import 'onboarding_screen.dart';

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, state, _) {
        if (!state.authReady) {
          return const _ThreeJsSplashLoading();
        }

        if (state.token == null) {
          return const OnboardingScreen();
        }

        return const HomeShell();
      },
    );
  }
}

class _ThreeJsSplashLoading extends StatefulWidget {
  const _ThreeJsSplashLoading();

  @override
  State<_ThreeJsSplashLoading> createState() => _ThreeJsSplashLoadingState();
}

class _ThreeJsSplashLoadingState extends State<_ThreeJsSplashLoading> {
  late final WebViewController _controller;

  static const String _html = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width,initial-scale=1.0" name="viewport"/>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body {
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #000;
}
#threejs-container-ANIMATION_4 {
  width: 100vw;
  height: 100vh;
}
</style>
</head>
<body>
<div id="threejs-container-ANIMATION_4"></div>
<script src="https://ajax.googleapis.com/ajax/libs/threejs/r125/three.min.js"></script>
<script>
(function() {
  const container = document.getElementById('threejs-container-ANIMATION_4');
  const width = container.clientWidth || window.innerWidth;
  const height = container.clientHeight || window.innerHeight;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });

  renderer.setSize(width, height);
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  container.appendChild(renderer.domElement);

  const geometry = new THREE.IcosahedronGeometry(1.5, 64);
  const material = new THREE.MeshPhongMaterial({
    color: 0x9D7BB0,
    emissive: 0x9D7BB0,
    emissiveIntensity: 0.5,
    shininess: 100,
    transparent: true,
    opacity: 0.8
  });

  const orb = new THREE.Mesh(geometry, material);
  scene.add(orb);

  const light = new THREE.PointLight(0xffffff, 1, 100);
  light.position.set(5, 5, 5);
  scene.add(light);
  scene.add(new THREE.AmbientLight(0xffffff, 0.5));

  camera.position.z = 5;

  const originalPositions = geometry.attributes.position.array.slice();
  let time = 0;

  function animate() {
    requestAnimationFrame(animate);
    time += 0.02;

    const positions = geometry.attributes.position.array;
    for (let i = 0; i < positions.length; i += 3) {
      const x = originalPositions[i];
      const y = originalPositions[i + 1];
      const z = originalPositions[i + 2];

      const noise =
        Math.sin(x * 2 + time) *
        Math.cos(y * 2 + time) *
        Math.sin(z * 2 + time) *
        0.3;

      positions[i] = x * (1 + noise);
      positions[i + 1] = y * (1 + noise);
      positions[i + 2] = z * (1 + noise);
    }

    geometry.attributes.position.needsUpdate = true;
    orb.rotation.y += 0.005;
    renderer.render(scene, camera);
  }

  window.addEventListener('resize', () => {
    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  });

  animate();
})();
</script>
</body>
</html>
''';

  @override
  void initState() {
    super.initState();

    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..loadHtmlString(_html);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: WebViewWidget(controller: _controller),
    );
  }
}
