# StudyAI dashboard design integration

This branch brings the supplied dashboard composition into the existing StudyAI app, rather than replacing the app with a standalone prototype.

## What's included

- Reference layout: greeting with 3D learning core, four KPI cards, learning journey and revision plan, recent notes and activity heat map, topic mastery and recommendations, quiz performance and study focus.
- Three.js / React Three Fiber visual elements in the existing teal, cyan, mint, and restrained peach palette.
- Scoped stylesheet so existing app pages retain their styles.
- Existing app shell hides its previous sidebar and topbar only on the dashboard view, avoiding duplicate navigation; other views keep their current shell.

## Live project connections

- `/dashboard` supplies learner profile, streak, KPI data, mastery topics, activity heat map, recommendations, and analytics.
- `/notes` supplies recent notes; selecting a note opens the existing Notes view and passes its id when present.
- `/quiz/attempts` supplies the quiz trend line, with the dashboard performance-history data as a fallback.
- `/planner` supplies pending revision tasks; actions open the existing Revision Planner.
- Existing `App.jsx` navigation and activity logging are retained. Upload, notes, quiz, Learn & Ask, and planner are still their existing separate views.

The study-time figure is labeled as an estimate because the current backend derives minutes from activity events rather than recording an actual timer. Settings and Plus are placeholders because this version of the app has no corresponding pages/subscription flow.

## Install and verify

From the `frontend` directory, run `npm install` to refresh the npm lockfile for the added packages, then `npm run dev` and `npm run build`. The runtime uses the existing React 18 / Vite 5 setup with compatible Three.js dependencies. A full production build has not been run in this environment because package registry access was unavailable.