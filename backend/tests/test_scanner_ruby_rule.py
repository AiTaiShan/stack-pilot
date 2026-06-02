import os
import pytest
from app.services.scanner.rules.ruby_rule import RubyRule
from app.services.scanner.rules.context import ProjectContext


def test_detect_language_with_gemfile():
    assert RubyRule.detect_language(["Gemfile"]) >= 0.5


def test_detect_language_with_rakefile():
    assert RubyRule.detect_language(["Rakefile"]) >= 0.5


def test_detect_language_without_ruby_files():
    assert RubyRule.detect_language(["package.json"]) < 0.5


def test_detect_language_with_gemfile_lock():
    assert RubyRule.detect_language(["Gemfile.lock"]) >= 0.5


def test_detect_rails_framework(tmpdir):
    gemfile_path = os.path.join(str(tmpdir), "Gemfile")
    with open(gemfile_path, "w") as f:
        f.write('source "https://rubygems.org"\n')
        f.write('gem "rails", "~> 7.0"\n')
        f.write('gem "puma"\n')
    config_ru_path = os.path.join(str(tmpdir), "config.ru")
    with open(config_ru_path, "w") as f:
        f.write("require './app'\nrun App\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["framework"] == "rails"
    assert result["entry_point"] == "config.ru"
    assert result["start_command"] == "bundle exec rails server -b 0.0.0.0 -p 3000"


def test_detect_sinatra_framework(tmpdir):
    gemfile_path = os.path.join(str(tmpdir), "Gemfile")
    with open(gemfile_path, "w") as f:
        f.write('source "https://rubygems.org"\n')
        f.write('gem "sinatra"\n')
        f.write('gem "puma"\n')
    app_path = os.path.join(str(tmpdir), "app.rb")
    with open(app_path, "w") as f:
        f.write("require 'sinatra'\n")
        f.write("get '/' do\n")
        f.write("  'Hello'\n")
        f.write("end\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["framework"] == "sinatra"
    assert result["entry_point"] == "app.rb"
    assert result["start_command"] == "ruby app.rb"


def test_detect_no_framework(tmpdir):
    gemfile_path = os.path.join(str(tmpdir), "Gemfile")
    with open(gemfile_path, "w") as f:
        f.write('source "https://rubygems.org"\n')
        f.write('gem "puma"\n')
    app_path = os.path.join(str(tmpdir), "app.rb")
    with open(app_path, "w") as f:
        f.write("puts 'Hello'\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["framework"] == ""


def test_detect_entry_point_config_ru(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    with open(os.path.join(str(tmpdir), "config.ru"), "w") as f:
        f.write("require './app'\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["entry_point"] == "config.ru"


def test_detect_entry_point_app_rb(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    with open(os.path.join(str(tmpdir), "app.rb"), "w") as f:
        f.write("puts 'hello'\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["entry_point"] == "app.rb"


def test_detect_entry_point_server_rb(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    with open(os.path.join(str(tmpdir), "server.rb"), "w") as f:
        f.write("puts 'hello'\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["entry_point"] == "server.rb"


def test_detect_entry_point_no_ruby_entry(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["entry_point"] is None


def test_detect_bundler_package_manager(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    with open(os.path.join(str(tmpdir), "Gemfile.lock"), "w") as f:
        f.write("GEM\n  remote: https://rubygems.org/\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["package_manager"] == "bundler"


def test_detect_default_package_manager_without_lock(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["package_manager"] == "bundler"


def test_detect_build_command(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["build_command"] == "bundle install"


def test_detect_start_command_generic(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    with open(os.path.join(str(tmpdir), "app.rb"), "w") as f:
        f.write("puts 'hello'\n")
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["start_command"] == "ruby app.rb"


def test_default_port(tmpdir):
    with open(os.path.join(str(tmpdir), "Gemfile"), "w") as f:
        f.write('source "https://rubygems.org"\n')
    ctx = ProjectContext(str(tmpdir))
    result = RubyRule.detect(ctx)
    assert result["port"] == 3000


def test_language_id():
    assert RubyRule.language_id() == "ruby"


def test_get_template_name():
    assert RubyRule.get_template_name() == "ruby_template"
