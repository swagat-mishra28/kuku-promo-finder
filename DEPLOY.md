# Deploy

Nothing has been pushed. Do these steps yourself, in order.

## 1. Push the code to GitHub

1. On github.com, click **New repository**. Name it `kuku-promo-finder`, set it to **Public**, and leave every "Initialize" box unticked (no README, no .gitignore, no licence).
2. In a terminal in the project folder:

```bash
cd E:\Downloads\kuku-promo-finder\kuku-promo-finder
git status                      # should say "nothing to commit, working tree clean"
git ls-files                    # check: no data/episodes/*.txt, no outputs/, no .env, no review_sheet.md
git branch -M main
git remote add origin https://github.com/<your-username>/kuku-promo-finder.git
git push -u origin main
```

3. Open the repo page and check that `data/episodes/` holds only `.gitkeep` and that there is no `outputs/` folder.

## 2. Deploy on Streamlit Community Cloud

1. Go to share.streamlit.io and sign in with GitHub.
2. Click **Create app**, then **Deploy a public app from GitHub**.
3. Repository: `<your-username>/kuku-promo-finder`. Branch: `main`. Main file path: `app.py`.
4. Click **Advanced settings**. Python version: 3.12 or newer. In **Secrets**, paste (only if you want the LLM mode online; rules-only needs nothing):

```toml
PROMO_LLM_PROVIDER = "groq"
PROMO_LLM_MODEL = "openai/gpt-oss-120b"
PROMO_LLM_API_KEY = "your-groq-key"
```

   If you put a key here, anyone with the app link can spend your free daily quota. Leaving Secrets empty keeps the app in rules-only mode by default, and visitors can paste their own key in the sidebar.
5. Click **Deploy**. The first build takes a few minutes.
6. Test it: open the app in a private window, upload two or three episode `.txt` files (or a `.zip`), keep provider `none`, click **Find promos**. You should see the table and the download buttons.

## 3. Raw outputs on Google Drive

1. Upload `raw_outputs_for_drive.zip` (project root, about 280 KB) to Google Drive.
2. Right-click, **Share**, then under General access choose **Anyone with the link**, role **Viewer**. Copy the link.
3. The zip quotes the confidential screenplays. Share the link only in the submission form.

## 4. Check every link

Open each link (GitHub repo, Streamlit app, Drive zip, solution doc) in a private browser window, signed out, before you submit.
