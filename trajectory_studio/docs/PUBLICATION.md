# Publication checklist

1. Keep the original clone and working local datasets as a private backup. Use this clean standalone folder for a new repository, not the original remote or history.
2. Verify ownership and redistribution rights for the code. The upstream CityTrack licence was not confirmed; no original ANPR folder, weights, or media are included. Review any additional code you add.
3. Review Ultralytics licensing at https://www.ultralytics.com/license and choose an appropriate licence. AGPL-3.0 is the proposed public source option, not a licence already granted by this package. Once authorized, add the full applicable licence text as LICENSE, e.g. using GitHub's licence chooser. Do not assume that credit alone grants redistribution permission.
4. Keep map attribution visible and follow https://www.openstreetmap.org/copyright and https://operations.osmfoundation.org/policies/tiles/.
5. Check screenshots for personal data and rights. Only a synthetic demo screenshot is included. Do not upload real clip footage, individual movement records, credentials, model weights, or local databases.
6. In the clean folder, run the tests and fresh setup from README.md. Verify all five pages after creating a local video report. Fix startup errors before making the repository public.
7. Create a new private, empty GitHub repository. From this folder (PowerShell):

```powershell
git init
git branch -M main
git add .
git status --short
git diff --cached --stat
git commit -m "Initial CityTrack prototype release"
git remote add origin https://github.com/YOUR_USERNAME/CityTrack-AI-Trajectory-System.git
git push -u origin main
```

Replace YOUR_USERNAME with your account name. Do not stage any unrelated files. If Git requests identity, configure your own name and email (a GitHub noreply address is an option). After reviewing rights, tests and the files actually pushed, change repository visibility to public if desired. No GitHub repository has been created or pushed by this package.
