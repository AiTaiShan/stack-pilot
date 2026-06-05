use std::path::PathBuf;
use std::collections::HashMap;
use std::sync::Mutex;
use tokio::fs;

pub struct ProjectContext {
    pub dir_path: PathBuf,
    files: Mutex<HashMap<String, String>>,
}

impl ProjectContext {
    pub fn new(dir_path: PathBuf) -> Self {
        Self {
            dir_path,
            files: Mutex::new(HashMap::new()),
        }
    }

    pub async fn list_dir(&self, relative_path: &str) -> Result<(Vec<String>, Vec<String>), std::io::Error> {
        let dir = self.dir_path.join(relative_path);
        let mut files = Vec::new();
        let mut dirs = Vec::new();

        let mut entries = fs::read_dir(dir).await?;
        while let Some(entry) = entries.next_entry().await? {
            let name = entry.file_name().to_string_lossy().to_string();
            if entry.file_type().await?.is_dir() {
                dirs.push(name);
            } else {
                files.push(name);
            }
        }

        Ok((files, dirs))
    }

    pub async fn read_text(&self, relative_path: &str) -> Option<String> {
        {
            let cache = self.files.lock().unwrap();
            if let Some(content) = cache.get(relative_path) {
                return Some(content.clone());
            }
        }

        let path = self.dir_path.join(relative_path);
        match fs::read_to_string(&path).await {
            Ok(content) => {
                let mut cache = self.files.lock().unwrap();
                cache.insert(relative_path.to_string(), content.clone());
                Some(content)
            }
            Err(_) => None,
        }
    }
}
