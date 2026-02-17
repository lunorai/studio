import { SidebarMenu } from "../../components/SidebarMenu/SidebarMenu";
import { Redirect } from "react-router-dom";
import { useCurrentUser } from "../../providers/CurrentUser";
import { PeoplePage } from "./PeoplePage/PeoplePage";
import { WebhookPage } from "../WebhookPage/WebhookPage";

const ALLOW_ORGANIZATION_WEBHOOKS =
  window.APP_SETTINGS.flags?.allow_organization_webhooks;

const MenuLayout = ({ children, ...routeProps }) => {
  const { user } = useCurrentUser();
  const isOrganizationOwner =
    Boolean(user?.isOwner) ||
    (Boolean(user?.active_organization_meta?.email) &&
      user?.email === user?.active_organization_meta?.email);
  const isOrganizationAdmin =
    user?.active_organization_membership?.role === "AD";
  const canAccessOrganization = isOrganizationOwner || isOrganizationAdmin;

  if (!canAccessOrganization) {
    return <Redirect to="/projects" />;
  }

  const menuItems = [PeoplePage];

  if (ALLOW_ORGANIZATION_WEBHOOKS) {
    menuItems.push(WebhookPage);
  }
  return (
    <SidebarMenu
      menuItems={menuItems}
      path={routeProps.match.url}
      children={children}
    />
  );
};

const organizationPages = {};

if (ALLOW_ORGANIZATION_WEBHOOKS) {
  organizationPages[WebhookPage] = WebhookPage;
}

export const OrganizationPage = {
  title: "Organization",
  path: "/organization",
  exact: true,
  layout: MenuLayout,
  component: PeoplePage,
  pages: organizationPages,
};
