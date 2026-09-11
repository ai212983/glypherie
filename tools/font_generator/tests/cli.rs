use serde_json::json;
use std::{fs, path::PathBuf, process::Command};

struct Scratch(PathBuf);
impl Scratch {
    fn new() -> Self {
        let path =
            std::env::temp_dir().join(format!("font-generator-tests-{}", std::process::id()));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }
}
impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn cli_resolves_fonts_relative_to_job_and_validates_before_writing() {
    let temp = Scratch::new();
    let source = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../font_probe/fonts/Roboto.ttf");
    fs::copy(source, temp.0.join("font.ttf")).unwrap();
    let job_path = temp.0.join("job.json");
    let output_path = temp.0.join("output.json");
    let mut job = json!({
        "font": "font.ttf",
        "provenance": {
            "source": "existing repository calibration font",
            "license": "SIL Open Font License 1.1 (embedded metadata)",
            "expected_sha256": "d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134"
        },
        "settings": {"size_px": 24.0, "characters": "AV0"}
    });
    let run = || {
        Command::new(env!("CARGO_BIN_EXE_font_generator"))
            .current_dir(std::env::temp_dir())
            .arg(&job_path)
            .arg(&output_path)
            .output()
            .unwrap()
    };
    fs::write(&job_path, serde_json::to_vec(&job).unwrap()).unwrap();
    let result = run();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let first = fs::read(&output_path).unwrap();
    assert!(run().status.success());
    assert_eq!(first, fs::read(&output_path).unwrap());
    job["provenance"]["expected_sha256"] = json!("wrong");
    fs::write(&job_path, serde_json::to_vec(&job).unwrap()).unwrap();
    let failed = run();
    assert!(!failed.status.success());
    assert!(String::from_utf8_lossy(&failed.stderr).contains("checksum mismatch"));
    assert_eq!(first, fs::read(&output_path).unwrap());
    fs::remove_file(&output_path).unwrap();
    assert!(!run().status.success());
    assert!(!output_path.exists());
}
