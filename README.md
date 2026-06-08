# Curriculum Advisor

A beginner-friendly Streamlit app for UCT Humanities curriculum guidance.

## What it does
- Loads UCT Humanities course data from `courses.json`
- Uses programme/major rules from `degree_requirements.json`
- Lets students select majors and mark completed courses
- Shows likely degree classification and progress indicators

## Run locally
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Deploy to Streamlit Community Cloud (recommended)
1. Create a GitHub repository and push this project.
2. Go to https://streamlit.io/cloud and connect your GitHub account.
3. Create a new app from the repo.
4. Set the main file to `app.py`.

Streamlit Cloud will install `requirements.txt` automatically and host the app for you.

## Alternative hosting
If you want a more general Python host, use a service like Render, Railway, or Heroku.

This project already includes:
- `requirements.txt`
- `app.py`
- `courses.json`
- `degree_requirements.json`

## Notes
- No extra Python installation is needed for viewers once the app is hosted.
- If you want, I can also set up the GitHub repo metadata and deployment workflow next.