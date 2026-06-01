"""Java 语言检测规则测试"""
import os
import pytest
from app.services.scanner.rules.java_rule import JavaRule


def test_detect_language_with_pom_xml():
    assert JavaRule.detect_language(["pom.xml"]) == True


def test_detect_language_with_build_gradle():
    assert JavaRule.detect_language(["build.gradle"]) == True


def test_detect_language_without_java_files():
    assert JavaRule.detect_language(["package.json"]) == False
    assert JavaRule.detect_language(["requirements.txt"]) == False


def test_detect_basic_java_app(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("""<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>myapp</artifactId>
  <version>1.0.0</version>
</project>""")
    src_dir = os.path.join(str(tmpdir), "src", "main", "java", "com", "example")
    os.makedirs(src_dir)
    app_path = os.path.join(src_dir, "Application.java")
    with open(app_path, "w") as f:
        f.write("""package com.example;

public class Application {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}""")
    result = JavaRule.detect(str(tmpdir))
    assert result["language"] == "java"
    assert result["entry_point"] == "com.example.Application"
    assert result["package_manager"] == "maven"
    assert result["build_command"] == "mvn package -DskipTests"
    assert result["start_command"] == "java -jar target/myapp-1.0.0.jar"
    assert result["port"] == 8080


def test_detect_spring_boot_framework(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("""<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>""")
    result = JavaRule.detect(str(tmpdir))
    assert result["framework"] == "spring-boot"


def test_detect_spring_boot_with_annotation(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("""<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
</project>""")
    src_dir = os.path.join(str(tmpdir), "src", "main", "java", "com", "example")
    os.makedirs(src_dir)
    app_path = os.path.join(src_dir, "DemoApplication.java")
    with open(app_path, "w") as f:
        f.write("""package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}""")
    result = JavaRule.detect(str(tmpdir))
    assert result["entry_point"] == "com.example.DemoApplication"


def test_detect_mybatis_framework(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("""<project>
  <dependencies>
    <dependency>
      <groupId>org.mybatis.spring.boot</groupId>
      <artifactId>mybatis-spring-boot-starter</artifactId>
      <version>3.0.0</version>
    </dependency>
  </dependencies>
</project>""")
    result = JavaRule.detect(str(tmpdir))
    assert result["framework"] == "mybatis"


def test_detect_quarkus_framework(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("""<project>
  <dependencies>
    <dependency>
      <groupId>io.quarkus</groupId>
      <artifactId>quarkus-core</artifactId>
    </dependency>
  </dependencies>
</project>""")
    result = JavaRule.detect(str(tmpdir))
    assert result["framework"] == "quarkus"


def test_detect_gradle_project(tmpdir):
    gradle_path = os.path.join(str(tmpdir), "build.gradle")
    with open(gradle_path, "w") as f:
        f.write("""plugins {
    id 'java'
    id 'org.springframework.boot' version '3.2.0'
}

group = 'com.example'
version = '1.0.0'

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}""")
    src_dir = os.path.join(str(tmpdir), "src", "main", "java", "com", "example")
    os.makedirs(src_dir)
    app_path = os.path.join(src_dir, "App.java")
    with open(app_path, "w") as f:
        f.write("""package com.example;

public class App {
    public static void main(String[] args) {}
}""")
    result = JavaRule.detect(str(tmpdir))
    assert result["language"] == "java"
    assert result["package_manager"] == "gradle"
    assert result["build_command"] == "gradle build"
    assert result["framework"] == "spring-boot"


def test_detect_port_from_application_properties(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("<project></project>")
    res_dir = os.path.join(str(tmpdir), "src", "main", "resources")
    os.makedirs(res_dir)
    prop_path = os.path.join(res_dir, "application.properties")
    with open(prop_path, "w") as f:
        f.write("server.port=9090\nspring.application.name=test\n")
    result = JavaRule.detect(str(tmpdir))
    assert result["port"] == 9090


def test_detect_port_from_application_yml(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("<project></project>")
    res_dir = os.path.join(str(tmpdir), "src", "main", "resources")
    os.makedirs(res_dir)
    yml_path = os.path.join(res_dir, "application.yml")
    with open(yml_path, "w") as f:
        f.write("server:\n  port: 8081\n")
    result = JavaRule.detect(str(tmpdir))
    assert result["port"] == 8081


def test_detect_default_port(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("<project></project>")
    result = JavaRule.detect(str(tmpdir))
    assert result["port"] == 8080


def test_no_main_class_found(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("<project></project>")
    src_dir = os.path.join(str(tmpdir), "src", "main", "java", "com", "example")
    os.makedirs(src_dir)
    util_path = os.path.join(src_dir, "Util.java")
    with open(util_path, "w") as f:
        f.write("""package com.example;

public class Util {
    public static String helper() { return "ok"; }
}""")
    result = JavaRule.detect(str(tmpdir))
    assert result["entry_point"] is None


def test_detect_no_src_main_java(tmpdir):
    pom_path = os.path.join(str(tmpdir), "pom.xml")
    with open(pom_path, "w") as f:
        f.write("<project></project>")
    result = JavaRule.detect(str(tmpdir))
    assert result["entry_point"] is None


def test_language_id():
    assert JavaRule.language_id() == "java"


def test_get_template_name():
    assert JavaRule.get_template_name() == "java_template"
