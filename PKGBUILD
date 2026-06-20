# Maintainer: souvikpng
pkgname=tenpad
pkgver=0.1.0
pkgrel=2
pkgdesc="Toggle a right-hand keyboard cluster into numpad keys"
arch=(any)
url="https://github.com/souvikpng/tenpad"
license=(custom)
depends=(python python-evdev)
makedepends=(python-build python-installer python-setuptools python-wheel)
source=()
sha256sums=()

build() {
  cd "$startdir"
  python -m build --wheel --no-isolation --outdir "$srcdir/dist"
}

package() {
  cd "$startdir"
  python -m installer --destdir="$pkgdir" "$srcdir"/dist/*.whl
}
