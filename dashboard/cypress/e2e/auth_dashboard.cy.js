describe("AutoReach demo login", () => {
  it("clears stale tokens and signs into the demo dashboard", () => {
    cy.visit("/login", {
      onBeforeLoad(win) {
        win.localStorage.setItem("autoreach_access_token", "stale-token");
        win.localStorage.setItem("autoreach_refresh_token", "stale-refresh");
      },
    });

    cy.contains("Welcome back").should("be.visible");
    cy.contains("Session expired").should("not.exist");
    cy.window().its("localStorage.autoreach_access_token").should("not.exist");

    cy.contains("button", "Use demo account").click();
    cy.contains("button", "Sign in").click();

    cy.location("pathname").should("match", /^\/app\/?$/);
    cy.contains("Dashboard").should("be.visible");
    cy.contains("SaaS Founders Q3").should("be.visible");
    cy.contains("Agency Outreach").should("be.visible");
    cy.window().its("localStorage.autoreach_access_token").should("exist");
  });
});
