# Development

This repository is the development source for `xhs-vn-post`. Keep the skill entry point at the repository root and its resources in `scripts/`, `references/`, and `examples/`.

- Preserve the local-only generation boundary and explicit user review before social-platform publishing. Never treat verification as publishing approval.
- Keep configuration paths relative to the configuration file and preserve dialogue without rewriting or truncation.
- Update `references/config.md` and `examples/post.example.json` when changing the configuration contract.
- Run `python -m unittest discover -s scripts -p "test_*.py" -v` after script changes. Tests need Pillow and a Chinese font; Linux uses Noto CJK.
- Do not commit personal assets, review packages, account credentials, cookies, or installed-client configuration. Use ignored `work/` for local projects.
- Installed skills may link to this checkout. Treat linked installs as the same source and preserve existing links; change installation locations only when requested.
