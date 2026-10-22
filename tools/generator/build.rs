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

fn dependency_field(lock: &str, name: &str, field: &str) -> String {
    let name = format!("name = \"{name}\"");
    let field = format!("{field} = \"");
    let mut selected = false;
    for line in lock.lines().map(str::trim) {
        if line == name {
            selected = true;
        } else if selected && line.starts_with(&field) {
            return line.trim_start_matches(&field).trim_end_matches('"').into();
        } else if line == "[[package]]" {
            selected = false;
        }
    }
    "unknown".into()
}

fn main() {
    // Build provenance is immutable; report construction must not parse the
    // dependency lock or hash its contents once per glyph.
    let lock = fs::read_to_string("Cargo.lock").unwrap();
    println!("cargo:rerun-if-changed=Cargo.lock");
    println!(
        "cargo:rustc-env=GENERATOR_LOCK_SHA256={:x}",
        Sha256::digest(&lock)
    );
    for (key, name, field) in [
        ("GENERATOR_SKRIFA_VERSION", "skrifa", "version"),
        ("GENERATOR_SKRIFA_CHECKSUM", "skrifa", "checksum"),
        ("GENERATOR_ZENO_VERSION", "zeno", "version"),
    ] {
        println!(
            "cargo:rustc-env={key}={}",
            dependency_field(&lock, name, field)
        );
    }

    // Keep the baseline identity independent of candidate dependencies.
    renderer("baseline");
    #[cfg(feature = "candidate")]
    {
        renderer("scan");
        let root = Path::new("vendor/freetype-mono");
        let mut hash = Sha256::new();
        collect(root, root, &mut hash);
        println!("cargo:rerun-if-changed={}", root.display());
        println!("cargo:rustc-env=FREETYPE_MONO_SHA256={:x}", hash.finalize());
        let mut compiler = cc::Build::new();
        compiler.file(root.join("adapter.c")).include(root);
        if std::env::var("TARGET").unwrap().starts_with("wasm32-") {
            compiler.flag("-ffreestanding");
        }
        compiler.compile("font_freetype_mono");
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
