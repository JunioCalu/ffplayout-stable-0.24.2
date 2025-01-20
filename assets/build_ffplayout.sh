rm -rv /config/workspace/ffplayout-dev/frontend/.output/
cd /config/workspace/ffplayout-dev/frontend/
npm run generate
cd /config/workspace/ffplayout-dev/
cargo clean
cargo build --locked --target=x86_64-unknown-linux-musl
cargo build --release --locked --target=x86_64-unknown-linux-musl
cargo deb --no-build --target=x86_64-unknown-linux-musl -p ffplayout --manifest-path=engine/Cargo.toml -o ffplayout_0.25.0-alpha4_junio_calu-1_amd64.deb
cargo generate-rpm --target=x86_64-unknown-linux-musl -p engine -o ffplayout-0.25.0-alpha4_junio_calu-1.x86_64.rpm
