// Public rendering helpers. Content is sourced exclusively from team-data.json.

async function renderHome() {
  try {
    const data = await getTeamData();
    const selectedProject = data.projects.find(
      (project) => project.id === data.planningPresentation.selectedProjectId
    );

    setText("site-course", data.site.course);
    setText("site-tagline", data.site.tagline);
    setText("site-description", data.site.description);
    setText("site-term", data.site.term);
    setText("selected-project-title", selectedProject?.title || "Selected project");
    setText("selected-project-description", selectedProject?.description || "");

    renderHomeTeam(data.members);
    renderHomeProjects(data.projects);
  } catch (error) {
    showDataError(error);
  }
}

function renderHomeTeam(members) {
  const grid = document.getElementById("home-team-grid");
  if (!grid) return;

  grid.innerHTML = members
    .map(
      (member, index) => `
        <article class="person-row">
          <span class="person-index">0${index + 1}</span>
          <div class="person-monogram" aria-hidden="true">${escapeHtml(memberInitials(member.name))}</div>
          <div class="person-copy">
            <h3>${escapeHtml(member.name)}</h3>
            <p>${escapeHtml(member.role)}</p>
          </div>
          <a class="text-link" href="members/member${member.id}.html" aria-label="View ${escapeHtml(member.name)} profile">Profile <span>↗</span></a>
        </article>
      `
    )
    .join("");
}

function renderHomeProjects(projects) {
  const grid = document.getElementById("home-project-grid");
  if (!grid) return;

  grid.innerHTML = projects
    .map(
      (project) => `
        <article class="proposal-row ${project.id === 1 ? "proposal-selected" : ""}">
          <div class="proposal-number">${escapeHtml(project.number)}</div>
          <div class="proposal-copy">
            <div class="proposal-meta">
              <span>${escapeHtml(project.status)}</span>
              <span>${escapeHtml(project.version)}</span>
            </div>
            <h3>${escapeHtml(project.title)}</h3>
            <p>${escapeHtml(project.description)}</p>
          </div>
          <a class="round-link" href="projects/project${project.id}.html" aria-label="Open ${escapeHtml(project.title)} presentation">↗</a>
        </article>
      `
    )
    .join("");
}

async function renderMember(id) {
  try {
    const data = await getTeamData();
    const member = data.members.find((item) => item.id === id);
    if (!member) throw new Error(`Member ${id} was not found.`);

    document.title = `${member.name} · ${data.site.name}`;
    setText("member-index", `Team member · 0${id}`);
    setText("avatar", memberInitials(member.name));
    setText("name", member.name);
    setText("role", member.role);
    setText("bio", member.bio);
    setText("strength", member.strength);
    setText("learning-goal", member.learningGoal);

    const skills = document.getElementById("skills");
    skills.innerHTML = member.skills
      .map((skill) => {
        const level = Math.min(100, Math.max(0, Number(skill.level) || 0));
        return `
          <div class="skill-row">
            <div class="skill-heading"><span>${escapeHtml(skill.name)}</span><span>${level}</span></div>
            <div class="skill-track"><span style="width:${level}%"></span></div>
          </div>
        `;
      })
      .join("");
  } catch (error) {
    showDataError(error);
  }
}

async function renderProject(id) {
  try {
    const data = await getTeamData();
    const project = data.projects.find((item) => item.id === id);
    if (!project) throw new Error(`Project ${id} was not found.`);

    document.title = `${project.title} · ${data.site.name}`;
    setText("project-number", `Proposal ${project.number}`);
    setText("project-status", project.status);
    setText("title", project.title);
    setText("description", project.description);
    setText("project-version", project.version);
    setText("project-date", project.date);
    setText("project-authors", project.authors.join(" · "));
    setText("project-decision", project.decision);

    const status = document.getElementById("project-status");
    if (status && project.id === data.planningPresentation.selectedProjectId) {
      status.classList.add("status-selected");
    }

    renderPresentationEmbed(project);
  } catch (error) {
    showDataError(error);
  }
}

async function renderPlanningPresentation(key = "planningPresentation") {
  try {
    const data = await getTeamData();
    const plan = data[key];
    if (!plan) throw new Error(`${key} was not found in the site data.`);
    const selectedProject = data.projects.find(
      (project) => project.id === plan.selectedProjectId
    );

    document.title = `${plan.title} · ${data.site.name}`;
    setText("planning-eyebrow", plan.eyebrow);
    setText("planning-title", plan.title);
    setText("planning-description", plan.description);
    setText("planning-version", plan.version);
    setText("planning-date", plan.date);
    setText("planning-status", plan.status);
    setText("planning-authors", plan.authors.join(" · "));
    setText("planning-change-summary", plan.changeSummary);
    setText("selected-project", selectedProject?.title || "Not configured");
    setText("selected-project-reason", selectedProject?.decision || "");
    setText("planning-scope", plan.scope);

    renderTags("planning-constraints", plan.constraints);
    renderPlainList("planning-objectives", plan.objectives);
    renderPlainList("planning-functions", plan.functions);
    renderPlainList("planning-users", plan.intendedUsers);
    renderPlainList("planning-interfaces", plan.externalInterfaces);

    document.getElementById("architecture-grid").innerHTML = plan.architecture
      .map(
        (layer) => `
          <article class="architecture-row">
            <span>${escapeHtml(layer.label)}</span>
            <h3>${escapeHtml(layer.title)}</h3>
            <p>${escapeHtml(layer.description)}</p>
          </article>
        `
      )
      .join("");

    document.getElementById("quality-grid").innerHTML = plan.qualityGoals
      .map(
        (goal) => `
          <article class="quality-block">
            <h3>${escapeHtml(goal.title)}</h3>
            <ul>${goal.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </article>
        `
      )
      .join("");

    document.getElementById("risks-list").innerHTML = plan.risks
      .map(
        (item, index) => `
          <article class="risk-row">
            <span>R${String(index + 1).padStart(2, "0")}</span>
            <h3>${escapeHtml(item.risk)}</h3>
            <p>${escapeHtml(item.response)}</p>
          </article>
        `
      )
      .join("");

    document.getElementById("milestone-list").innerHTML = plan.milestones
      .map(
        (milestone, index) => `
          <article class="milestone-row">
            <div class="milestone-marker"><span>${index + 1}</span></div>
            <div><p>${escapeHtml(milestone.period)}</p><h3>${escapeHtml(milestone.title)}</h3></div>
            <span class="milestone-owner">${escapeHtml(milestone.owner)}</span>
          </article>
        `
      )
      .join("");

    const changes = document.getElementById("changes-list");
    if (changes) {
      const items = plan.changesFromPrevious || [];
      changes.closest("section").hidden = items.length === 0;
      changes.innerHTML = items
        .map(
          (item) => `
            <article class="risk-row change-row change-${escapeHtml(item.label.toLowerCase())}">
              <span>${escapeHtml(item.label)}</span>
              <h3>${escapeHtml(item.title)}</h3>
              <p>${escapeHtml(item.description)}</p>
            </article>
          `
        )
        .join("");
    }

    document.getElementById("version-list").innerHTML = plan.versions
      .map(
        (version) => `
          <article class="version-row">
            <span class="version-name">${escapeHtml(version.version)}</span>
            <span>${escapeHtml(version.date)}</span>
            <span>${escapeHtml(version.status)}</span>
            <p>${escapeHtml(version.summary)}</p>
          </article>
        `
      )
      .join("");

    const memberIds = new Set(plan.teamMemberIds);
    document.getElementById("planning-team-grid").innerHTML = data.members
      .filter((member) => memberIds.has(member.id))
      .map(
        (member) => `
          <article class="plan-owner">
            <span>${escapeHtml(memberInitials(member.name))}</span>
            <div><h3>${escapeHtml(member.name)}</h3><p>${escapeHtml(member.role)}</p></div>
          </article>
        `
      )
      .join("");

    renderPresentationEmbed(plan);
  } catch (error) {
    showDataError(error);
  }
}

async function renderChangelog() {
  const target = document.getElementById("changelog-list");
  if (!target) return;

  try {
    const data = await getTeamData();
    const months = data.changelog || [];
    target.innerHTML = months
      .map(
        (month) => `
          <section class="log-month">
            <h3>${escapeHtml(month.month)}</h3>
            <ol class="log-list">
              ${month.entries
                .map(
                  (entry) => `
                    <li class="log-row">
                      <span class="log-date">${escapeHtml(entry.date)}</span>
                      <span class="log-area">${escapeHtml(entry.area)}</span>
                      <p>${escapeHtml(entry.text)}</p>
                    </li>
                  `
                )
                .join("")}
            </ol>
          </section>
        `
      )
      .join("");
  } catch (error) {
    showDataError(error);
  }
}

async function renderPublishedArchive() {
  const target = document.getElementById("published-list");
  if (!target) return;

  try {
    const response = await fetch(getSiteAssetUrl("content/index.json"), { cache: "no-store" });
    if (response.status === 404 || response.status === 403) {
      target.innerHTML = '<p class="archive-empty">Nothing has been published from the admin page yet.</p>';
      return;
    }
    if (!response.ok) throw new Error(`Could not load the published list (${response.status}).`);
    const index = await response.json();
    const items = index.deliverables || [];
    if (!items.length) {
      target.innerHTML = '<p class="archive-empty">Nothing has been published from the admin page yet.</p>';
      return;
    }
    target.innerHTML = items
      .map((item) => {
        const versions = item.versions || [];
        const latest = versions[0] || {};
        const older = versions
          .slice(1)
          .map((v) => `<a href="${escapeHtml(v.url)}">${escapeHtml(v.version)}</a>`)
          .join(", ");
        return `
          <article class="archive-row">
            <span class="archive-date">${escapeHtml(latest.date || "")}</span>
            <div>
              <h3><a href="${escapeHtml(latest.url || item.url)}">${escapeHtml(item.title)}</a></h3>
              <p>${escapeHtml(latest.changeSummary || "")}</p>
              <p class="archive-older"><a href="${escapeHtml(item.url)}">All versions</a>${older ? ` · Earlier: ${older}` : ""}</p>
            </div>
            <span class="archive-version">${escapeHtml(latest.version || "")}</span>
            <span class="archive-authors">${escapeHtml((latest.authors || []).join(" · "))}</span>
          </article>
        `;
      })
      .join("");
  } catch (error) {
    target.innerHTML = `<p class="archive-empty">${escapeHtml(error.message)}</p>`;
  }
}

function renderPresentationEmbed(presentation) {
  const wrapper = document.getElementById("embed-wrapper");
  const download = document.getElementById("download-link");
  if (!wrapper) return;

  if (!presentation.pptxUrl?.trim()) {
    wrapper.innerHTML = '<div class="embed-placeholder"><strong>No presentation is linked.</strong></div>';
    return;
  }

  const assetUrl = getSiteAssetUrl(presentation.pptxUrl.trim());
  const isLocalPreview =
    window.location.protocol === "file:" ||
    ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);

  if (isLocalPreview) {
    wrapper.innerHTML = `
      <div class="embed-placeholder">
        <span class="document-mark">PPTX</span>
        <strong>Embedded preview available after deployment</strong>
        <p>Microsoft Office Viewer needs a public URL. The source deck remains available through the download link.</p>
      </div>
    `;
  } else {
    const viewerUrl =
      "https://view.officeapps.live.com/op/embed.aspx?src=" + encodeURIComponent(assetUrl);
    wrapper.innerHTML = `<iframe src="${viewerUrl}" title="${escapeHtml(presentation.title)}" allowfullscreen></iframe>`;
  }

  if (download) {
    download.href = assetUrl;
    download.hidden = false;
  }
}

function renderTags(id, items) {
  const target = document.getElementById(id);
  if (!target) return;
  target.innerHTML = items.map((item) => `<span>${escapeHtml(item)}</span>`).join("");
}

function renderPlainList(id, items) {
  const target = document.getElementById(id);
  if (!target) return;
  target.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function setText(id, value) {
  const target = document.getElementById(id);
  if (target) target.textContent = value ?? "";
}

function memberInitials(name) {
  return (
    (name || "")
      .split(/\s+/)
      .filter(Boolean)
      .map((word) => word[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?"
  );
}

function showDataError(error, target = document.querySelector("main")) {
  console.error(error);
  if (!target) return;
  const message = document.createElement("div");
  message.className = "data-error";
  message.innerHTML = `<strong>Site data could not be loaded.</strong><p>${escapeHtml(error.message)}</p>`;
  target.prepend(message);
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value ?? "";
  return element.innerHTML;
}
