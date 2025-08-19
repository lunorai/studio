import { SidebarMenu } from "../../components/SidebarMenu/SidebarMenu";
import { WebhookPage } from "../WebhookPage/WebhookPage";
import { DangerZone } from "./DangerZone";
import { GeneralSettings } from "./GeneralSettings";
import { AnnotationSettings } from "./AnnotationSettings";
import { LabelingSettings } from "./LabelingSettings";
import { MachineLearningSettings } from "./MachineLearningSettings/MachineLearningSettings";
import { PredictionsSettings } from "./PredictionsSettings/PredictionsSettings";
import { StorageSettings } from "./StorageSettings/StorageSettings";
import { isInLicense, LF_CLOUD_STORAGE_FOR_MANAGERS } from "../../utils/license-flags";
import { Block } from "../../utils/bem";
import { useCurrentUser } from "../../providers/CurrentUser";
import "./settings.scss";

const isAllowCloudStorage = !isInLicense(LF_CLOUD_STORAGE_FOR_MANAGERS);

export const MenuLayout = ({ children, ...routeProps }) => {
  const { user } = useCurrentUser();
  const isOwner = Boolean(user?.isOwner) || (
    Boolean(user?.active_organization_meta?.email) && user?.email === user?.active_organization_meta?.email
  );

  if (!isOwner) {
    return (
      <Block name="settings-guard" style={{ padding: 24 }}>
        You don't have permission to access Settings. Please contact your organization owner.
      </Block>
    );
  }

  return (
    <SidebarMenu
      menuItems={[
        GeneralSettings,
        LabelingSettings,
        AnnotationSettings,
        MachineLearningSettings,
        PredictionsSettings,
        isAllowCloudStorage && StorageSettings,
        WebhookPage,
        DangerZone,
      ].filter(Boolean)}
      path={routeProps.match.url}
      children={children}
    />
  );
};

const pages = {
  AnnotationSettings,
  LabelingSettings,
  MachineLearningSettings,
  PredictionsSettings,
  WebhookPage,
  DangerZone,
};

isAllowCloudStorage && (pages.StorageSettings = StorageSettings);

export const SettingsPage = {
  title: "Settings",
  path: "/settings",
  exact: true,
  layout: MenuLayout,
  component: GeneralSettings,
  pages,
};
