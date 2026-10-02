use sha2::{Digest, Sha256};
use std::{fs, path::Path};

fn collect(root: &Path, directory: &Path, digest: &mut Sha256) {
    let mut entries: Vec<_> = fs::read_dir(directory)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .collect();
    entries.sort();
    for path in entries {
        if path.is_dir() {
            collect(root, &path, digest);
        } else {
            let relative = path.strip_prefix(root).unwrap().to_str().unwrap();
            let bytes = fs::read(&path).unwrap();
            digest.update((relative.len() as u64).to_le_bytes());
            digest.update(relative.as_bytes());
            digest.update((bytes.len() as u64).to_le_bytes());
            digest.update(bytes);
        }
    }
}

fn main() {
    for role in ["baseline", "candidate"] {
        renderer(role);
    }
}

fn renderer(role: &str) {
    let directory = format!("vendor/skrifa-{role}");
    let root = Path::new(&directory);
    let mut digest = Sha256::new();
    for name in [
        "src",
        "generated",
        "Cargo.toml",
        "LICENSE-MIT",
        "LICENSE-APACHE",
        "PATCH.md",
    ] {
        let path = root.join(name);
        println!("cargo:rerun-if-changed={}", path.display());
        if path.is_dir() {
            collect(root, &path, &mut digest);
        } else {
            let bytes = fs::read(&path).unwrap();
            digest.update((name.len() as u64).to_le_bytes());
            digest.update(name.as_bytes());
            digest.update((bytes.len() as u64).to_le_bytes());
            digest.update(bytes);
        }
    }
    println!(
        "cargo:rustc-env=SKRIFA_{}_SHA256={:x}",
        role.to_uppercase(),
        digest.finalize()
    );
}
