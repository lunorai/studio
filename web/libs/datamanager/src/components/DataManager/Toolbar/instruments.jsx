import { IconChevronDown } from "@humansignal/icons";
import { Block } from "../../../utils/bem";
import { FF_SELF_SERVE, isFF } from "../../../utils/feature-flags";
import { ErrorBox } from "../../Common/ErrorBox";
import { FieldsButton } from "../../Common/FieldsButton";
import { FiltersPane } from "../../Common/FiltersPane";
import { Icon } from "../../Common/Icon/Icon";
import { Interface } from "../../Common/Interface";
import { ExportButton, ImportButton } from "../../Common/SDKButtons";
import { Button } from "@humansignal/ui";
import { inject, observer } from "mobx-react";
import { useState } from "react";
import { Tooltip } from "@humansignal/ui";
import { ActionsButton } from "./ActionsButton";
import { GridWidthButton } from "./GridWidthButton";
import { LabelButton } from "./LabelButton";
import { LoadingPossum } from "./LoadingPossum";
import { OrderButton } from "./OrderButton";
import { RefreshButton } from "./RefreshButton";
import { ViewToggle } from "./ViewToggle";

const style = {
  minWidth: "80px",
  justifyContent: "space-between",
};

/**
 * Checks for Starter Cloud trial expiration.
 * If expired it renders disabled Import button with a tooltip.
 */
const ImportButtonWithChecks = ({ size }) => {
  const simpleButton = <ImportButton size={size}>Import</ImportButton>;
  const isOpenSource = !window.APP_SETTINGS.billing;
  // Check if user is self-serve; Enterprise flag === false is the main condition
  const isSelfServe = isFF(FF_SELF_SERVE) && window.APP_SETTINGS.billing?.enterprise === false;

  if (isOpenSource || !isSelfServe) return simpleButton;

  // Check if user is on trial
  const isTrialExpired = window.APP_SETTINGS.billing.checks?.is_license_expired;
  // Check the subscription period end date
  const subscriptionPeriodEnd = window.APP_SETTINGS.subscription?.current_period_end;
  // Check if user is self-serve and has expired trial
  const isSelfServeExpiredTrial = isSelfServe && isTrialExpired && !subscriptionPeriodEnd;
  // Check if user is self-serve and has expired subscription
  const isSelfServeExpiredSubscription =
    isSelfServe && subscriptionPeriodEnd && new Date(subscriptionPeriodEnd) < new Date();
  // Check if user is self-serve and has expired trial or subscription
  const isSelfServeExpired = isSelfServeExpiredTrial || isSelfServeExpiredSubscription;

  if (!isSelfServeExpired) return simpleButton;

  // Disabled buttons ignore hover, so we use wrapper to properly handle a tooltip
  return (
    <Tooltip
      title="You must upgrade your plan to import data"
      style={{
        maxWidth: 200,
        textAlign: "center",
      }}
    >
      <Block name="button-wrapper">
        <ImportButton disabled size={size}>
          Import
        </ImportButton>
      </Block>
    </Tooltip>
  );
};

export const instruments = {
  "view-toggle": ({ size }) => {
    return <ViewToggle size={size} style={style} />;
  },
  columns: ({ size }) => {
    const iconProps = {
      style: {
        marginRight: 4,
      },
      icon: IconChevronDown,
    };
    return (
      <FieldsButton
        wrapper={FieldsButton.Checkbox}
        trailingIcon={<Icon {...iconProps} />}
        title={"Columns"}
        size={size}
        style={style}
        openUpwardForShortViewport={false}
      />
    );
  },
  filters: ({ size }) => {
    return <FiltersPane size={size} style={style} />;
  },
  ordering: ({ size }) => {
    return <OrderButton size={size} style={style} />;
  },
  "grid-size": ({ size }) => {
    return <GridWidthButton size={size} />;
  },
  refresh: ({ size }) => {
    return <RefreshButton size={size} />;
  },
  "loading-possum": () => {
    return <LoadingPossum />;
  },
  "label-button": ({ size }) => {
    return <LabelButton size={size} />;
  },
  actions: ({ size }) => {
    return <ActionsButton size={size} style={style} />;
  },
  "error-box": () => {
    return <ErrorBox />;
  },
  "import-button": ({ size }) => {
    return (
      <Interface name="import">
        <ImportButtonWithChecks size={size} />
      </Interface>
    );
  },
  "export-button": ({ size }) => {
    return (
      <Interface name="export">
        <ExportButton size={size}>Export</ExportButton>
      </Interface>
    );
  },
  "export-my-annotations": ({ size }) => {
    const ExportMyAnnotationsButton = inject(({ store }) => ({ projectId: store?.project?.id, store }))(
      observer(({ projectId, store }) => {
        const [loading, setLoading] = useState(false);
        const currentUser = window.APP_SETTINGS?.user;
        const isOwner = Boolean(currentUser?.isOwner) || (
          Boolean(currentUser?.activeOrganizationMeta?.email) && currentUser?.email === currentUser?.activeOrganizationMeta?.email
        );

        if (isOwner) return null;

        const onClick = async () => {
          try {
            setLoading(true);
            const params = new URLSearchParams({ exportType: "CSV", annotations_by_me: "1" });
            const response = await fetch(`/api/projects/${projectId}/export?${params.toString()}`, {
              credentials: "include",
            });
            if (!response.ok) throw new Error(`${response.status}`);
            const blob = await response.blob();

            // Prepare upload params
            const app = window.APP_SETTINGS ?? {};
            
            const fallback = `annotations-${app?.user?.id || "me"}.csv`;
            const filename = (response.headers.get("filename") || fallback).replace(/\.json$/i, ".csv");
            const challengeId = Number(store?.project?.challenge_id ?? null);
            const round = store?.project?.round ?? 1;
            const userId = app?.user?.lunor_userId ?? '';

            const graphqlEndpoint = process.env.GRAPHQL_ENDPOINT || "https://dev.100protocol.com/";

            // GraphQL query to request an upload URL to R2
            const gqlQuery = `query($challengeId: Int!, $userId: String!, $round: Int!, $filename: String!) {\n  getAnnotationUploadUrl(challengeId: $challengeId, userId: $userId, round: $round, filename: $filename) {\n    challengeId\n    round\n    submissionId\n    maxConcurrentUploadLimit\n    urlArr { url key }\n  }\n}`;

            const gqlResp = await fetch(graphqlEndpoint, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                query: gqlQuery,
                variables: { challengeId, userId, round, filename },
              }),
              credentials: "include",
            });
            if (!gqlResp.ok) throw new Error(`GraphQL ${gqlResp.status}`);
            const gqlJson = await gqlResp.json();
            const uploadInfo = gqlJson?.data?.getAnnotationUploadUrl;
            const uploadUrl = uploadInfo?.urlArr?.[0]?.url;
            if (!uploadUrl) throw new Error("No upload URL returned");

            // Upload CSV blob to R2 using the signed URL
            const putResp = await fetch(uploadUrl, {
              method: "PUT",
              body: blob,
              headers: {
                "Content-Type": "text/csv",
              },
            });
            if (!putResp.ok) throw new Error(`Upload ${putResp.status}`);

            // After successful upload, notify backend with UpdateSubmissionAssetList
            // Use the key(s) returned by getAnnotationUploadUrl, do not use filename
            const assetKeys = Array.isArray(uploadInfo?.urlArr)
              ? uploadInfo.urlArr.map((item) => item?.key).filter(Boolean)
              : [];
            if (assetKeys.length === 0) throw new Error("No asset keys returned from getAnnotationUploadUrl");
            const updateMutation = `mutation UpdateSubmissionAssetList($submissionId: Int, $challengeId: Int, $round: Int, $userId: String!, $asset_list: [String!]!) {\n  updateSubmissionAssetList(\n    submissionId: $submissionId\n    challengeId: $challengeId\n    round: $round\n    userId: $userId\n    asset_list: $asset_list\n  )\n}`;

            const updateResp = await fetch(graphqlEndpoint, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: JSON.stringify({
                query: updateMutation,
                variables: {
                  submissionId: uploadInfo?.submissionId ?? null,
                  challengeId,
                  round,
                  userId,
                  asset_list: assetKeys,
                },
              }),
            });
            if (!updateResp.ok) throw new Error(`UpdateSubmissionAssetList ${updateResp.status}`);

            // Notify success
            store?.SDK?.invoke?.("toast", { message: "Submission uploaded successfully", type: "success" });
          } catch (err) {
            // eslint-disable-next-line no-console
            console.error("Failed to export annotations by me:", err);
            store?.SDK?.invoke?.("toast", { message: `Upload failed: ${String(err)}`.slice(0, 300), type: "error" });
          } finally {
            setLoading(false);
          }
        };
        const styleOverride = loading
          ? {
              "--wait-color-value": "#EABE00",
              "--wait-color-value-outline": "#EABE00",
              "--text-color": "#ccc",
            }
          : {
              "--wait-color-value": "#EABE00",
              "--wait-color-value-outline": "#EABE00",
            };

        return (
          <Button
            size={size}
            look="outlined"
            variant="primary"
            onClick={onClick}
            waiting={loading}
            disabled={loading}
            aria-label="End Annotation"
            style={styleOverride}
          >
            Final Submit
          </Button>
        );
      }),
    );
    return <Interface name="export"><ExportMyAnnotationsButton /></Interface>;
  },
};
