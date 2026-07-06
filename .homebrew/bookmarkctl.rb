# typed: false
# frozen_string_literal: true

class Bookmarkctl < Formula
  desc "Control Chrome bookmarks through a local FastAPI queue and CLI"
  homepage "https://github.com/{{REPOSITORY}}"
  url "{{URL}}"
  sha256 "{{SHA256}}"
  license "MIT"
  head "https://github.com/{{REPOSITORY}}.git", branch: "main"

  depends_on "uv"

  def install
    libexec.install "pyproject.toml", "src"
    (bin/"bookmarkctl").write <<~SH
      #!/bin/bash
      exec "#{formula_opt_bin("uv")}/uv" run --no-project --python 3.12 \
        --with 'bookmarkctl @ file://#{libexec}' \
        bookmarkctl "$@"
    SH
    chmod 0755, bin/"bookmarkctl"
  end

  test do
    assert_match "Manage Chrome bookmarks", shell_output("#{bin}/bookmarkctl --help")
  end
end
