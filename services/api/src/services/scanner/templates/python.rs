#![allow(dead_code)]
pub fn generate_python_dockerfile(framework: &str, version: &str, port: u16) -> String {
    let base_image = format!("python:{}-slim", version);

    match framework {
        "fastapi" => format!(
            r#"FROM {base_image}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE {port}

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "{port}"]
"#,
            base_image = base_image,
            port = port
        ),
        "flask" => format!(
            r#"FROM {base_image}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE {port}

CMD ["python", "app.py"]
"#,
            base_image = base_image,
            port = port
        ),
        _ => format!(
            r#"FROM {base_image}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE {port}

CMD ["python", "main.py"]
"#,
            base_image = base_image,
            port = port
        ),
    }
}
