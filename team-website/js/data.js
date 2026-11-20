// The committed JSON file is the single source of truth for all public pages.
// Resolve it relative to this script so the site works at a domain root, under
// GitHub Pages' /se-proj/ path, and from nested member/project pages.

const TEAM_DATA_URL = new URL("../data/team-data.json", document.currentScript.src).href;
let teamDataPromise = null;

function validateTeamData(data) {
  if (!data || !Array.isArray(data.members) || !Array.isArray(data.projects)) {
    throw new Error("data/team-data.json is missing the members or projects collection.");
  }

  if (!data.planningPresentation) {
    throw new Error("data/team-data.json is missing planningPresentation.");
  }

  return data;
}

async function getTeamData(options = {}) {
  if (options.fresh || !teamDataPromise) {
    teamDataPromise = fetch(TEAM_DATA_URL, { cache: options.fresh ? "no-store" : "default" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Could not load team data (${response.status}).`);
        }
        return response.json();
      })
      .then(validateTeamData)
      .catch((error) => {
        teamDataPromise = null;
        throw error;
      });
  }

  return teamDataPromise;
}

function getSiteAssetUrl(assetPath) {
  if (!assetPath) return "";
  if (/^https?:\/\//i.test(assetPath)) return assetPath;

  const cleanPath = assetPath.replace(/^\/+/, "");
  return new URL(`../${cleanPath}`, TEAM_DATA_URL).href;
}
