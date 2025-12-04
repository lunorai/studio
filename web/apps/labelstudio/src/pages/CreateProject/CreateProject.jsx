import { EnterpriseBadge, Select, Typography } from "@humansignal/ui";
import React from "react";
import { useHistory } from "react-router";
import { ToggleItems } from "../../components";
import { Button } from "@humansignal/ui";
import { Modal } from "../../components/Modal/Modal";
import { Space } from "../../components/Space/Space";
import { HeidiTips } from "../../components/HeidiTips/HeidiTips";
import { useAPI } from "../../providers/ApiProvider";
import { cn } from "../../utils/bem";
import { ConfigPage } from "./Config/Config";
import "./CreateProject.scss";
import { ImportPage } from "./Import/Import";
import { useImportPage } from "./Import/useImportPage";
import { useDraftProject } from "./utils/useDraftProject";
import { Input, TextArea } from "../../components/Form";
import { FF_LSDV_E_297, isFF } from "../../utils/feature-flags";
import { createURL } from "../../components/HeidiTips/utils";
import { useCurrentUser } from "../../providers/CurrentUser";

const ProjectName = ({
  name,
  setName,
  onSaveName,
  onSubmit,
  error,
  description,
  setDescription,
  show = true,
  challengeId,
  setChallengeId,
  round,
  setRound,
  selectedChallenge,
  onChallengeSelect,
  challenges,
  challengesLoading,
}) => {
  const hasChallengeOptions = challenges && challenges.length > 0;
  const lockFields = challengesLoading || hasChallengeOptions;

  if (!show) return null;

  return (
    <form
      className={cn("project-name")}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      {(challengesLoading || hasChallengeOptions) ?
          <div className="w-full flex flex-col gap-2">
            <label className="w-full" htmlFor="challenge_select">
              Select Quest
            </label>
            <Select
              id="challenge_select"
              name="challenge_select"
              placeholder={challengesLoading ? "Loading quests..." : "Select a quest"}
              options={challenges.map((challenge) => ({
                label: challenge.title + " - Round " + challenge.round,
                value: challenge.id,
                description: challenge.description,
              }))}
              value={selectedChallenge}
              onChange={onChallengeSelect}
              // triggerClassName="project-title w-full p-[20px]"
              triggerClassName="!flex-1"
              dataTestid="challenge-select"
              disabled={challengesLoading}
            />
          </div>
        : null
      }
      <div className="w-full flex flex-col gap-2">
        <label className="w-full" htmlFor="project_name">
          Project Name
        </label>
        <Input
          name="name"
          id="project_name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={onSaveName}
          className="project-title w-full"
          readOnly={lockFields}
        />
        {error && <span className="-mt-1 text-negative-content">{error}</span>}
      </div>
      <div className="w-full flex flex-col gap-2">
        <label className="w-full" htmlFor="project_description">
          Description
        </label>
        <TextArea
          name="description"
          id="project_description"
          placeholder="Optional description of your project"
          rows="4"
          style={{ minHeight: 100 }}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="project-description w-full"
          readOnly={lockFields}
        />
      </div>
      {!lockFields && (
        <>
          <div className="w-full flex flex-col gap-2">
            <label className="w-full" htmlFor="project_challenge_id">
              Challenge Id
            </label>
            <TextArea
              name="challenge_id"
              id="project_challenge_id"
              placeholder="Challenge ID of Lunor Quest"
              rows="4"
              style={{ minHeight: 100 }}
              value={challengeId}
              onChange={(e) => setChallengeId(e.target.value)}
              className="project-description w-full"
              required={true}
            />
          </div>
          <div className="w-full flex flex-col gap-2">
            <label className="w-full" htmlFor="round">
              Round
            </label>
            <TextArea
              name="round"
              id="project_round"
              placeholder="Round number of the challenge"
              rows="4"
              style={{ minHeight: 100 }}
              value={round}
              onChange={(e) => setRound(e.target.value)}
              className="project-description w-full"
              required={true}
            />
          </div>
        </>
      )}
      {isFF(FF_LSDV_E_297) && (
        // <div className="w-full flex flex-col gap-2">
        //   <label>
        //     Workspace
        //     <EnterpriseBadge className="ml-2" />
        //   </label>
        //   <Select placeholder="Select an option" disabled options={[]} triggerClassName="!flex-1" />
        //   {/* <Typography size="small" className="mt-tight mb-wider">
        //     Simplify project management by organizing projects into workspaces.{" "}
        //     <a
        //       href={createURL(
        //         "https://docs.humansignal.com/guide/manage_projects#Create-workspaces-to-organize-projects",
        //         {
        //           experiment: "project_creation_dropdown",
        //           treatment: "simplify_project_management",
        //         },
        //       )}
        //       target="_blank"
        //       rel="noreferrer"
        //       className="underline hover:no-underline text-[#EABE00]"
        //     >
        //       Learn more
        //     </a>
        //   </Typography> */}
        //   {/* <HeidiTips collection="projectCreation" /> */}
        // </div>
        null
      )}
    </form>
  );
};

export const CreateProject = ({ onClose }) => {
  const { user } = useCurrentUser();
  const isOwner = Boolean(user?.isOwner) || (
    Boolean(user?.active_organization_meta?.email) && user?.email === user?.active_organization_meta?.email
  );
  if (!isOwner) return null;

  const [step, _setStep] = React.useState("name"); // name | import | config
  const [waiting, setWaitingStatus] = React.useState(false);

  const { project, setProject: updateProject } = useDraftProject();
  const history = useHistory();
  const api = useAPI();

  const [name, setName] = React.useState("");
  const [error, setError] = React.useState();
  const [description, setDescription] = React.useState("");
  const [sample, setSample] = React.useState(null);
  const [challengeId, setChallengeId] = React.useState("");
  const [round, setRound] = React.useState("");
  const [selectedChallenge, setSelectedChallenge] = React.useState("");
  const [challenges, setChallenges] = React.useState([]);
  const [challengesLoading, setChallengesLoading] = React.useState(false);

  React.useEffect(() => {
    const GRAPHQL_ENDPOINT = process.env.GRAPHQL_ENDPOINT;
    const orgId = user?.lunor_userId;

    if (!GRAPHQL_ENDPOINT || !orgId) return;

    const query = `
      query FetchActiveChallengesForOrg($orgId: String!) {
        fetchActiveChallengesForOrg(orgId: $orgId) {
          id
          round
          summary
          title
        }
      }
    `;

    const fetchChallenges = async () => {
      setChallengesLoading(true);
      try {
        const response = await fetch(GRAPHQL_ENDPOINT, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ query, variables: { orgId } }),
        });

        if (!response.ok) {
          // eslint-disable-next-line no-console
          console.error("Failed to fetch challenges", response.statusText);
          setChallenges([]);
          return;
        }

        const json = await response.json();
        const fetched = json?.data?.fetchActiveChallengesForOrg ?? [];

        setChallenges(
          fetched.map((challenge) => ({
            id: challenge.id,
            title: challenge.title,
            description: challenge.summary,
            round: challenge.round,
          })),
        );
      } catch (error) {
        // eslint-disable-next-line no-console
        console.error("Error fetching challenges", error);
        setChallenges([]);
      } finally {
        setChallengesLoading(false);
      }
    };

    fetchChallenges();
  }, [user]);
  const handleChallengeSelect = React.useCallback(
    (value) => {
      const selected = challenges.find((challenge) => challenge.id === value);

      setSelectedChallenge(value);

      if (selected) {
        setName(selected.title ?? "");
        setDescription(selected.description ?? "");
        setChallengeId(selected.id ?? "");
        setRound(selected.round ?? "");
      } else {
        setName("");
        setDescription("");
        setChallengeId("");
        setRound("");
      }
    },
    [challenges, setName, setDescription, setChallengeId, setRound],
  );

  const setStep = React.useCallback((step) => {
    _setStep(step);
    const eventNameMap = {
      name: "project_name",
      import: "data_import",
      config: "labeling_setup",
    };
    __lsa(`create_project.tab.${eventNameMap[step]}`);
  }, []);

  React.useEffect(() => {
    setError(null);
  }, [name]);

  const { columns, uploading, uploadDisabled, finishUpload, pageProps, uploadSample } = useImportPage(project, sample);

  const rootClass = cn("create-project");
  const tabClass = rootClass.elem("tab");
  const steps = {
    name: <span className={tabClass.mod({ disabled: !!error })}>Project Name</span>,
    import: <span className={tabClass.mod({ disabled: uploadDisabled })}>Data Import</span>,
    config: "Labeling Setup",
  };

  // name intentionally skipped from deps:
  // this should trigger only once when we got project loaded
  React.useEffect(() => {
    project && !name && setName(project.title);
  }, [project]);

  const projectBody = React.useMemo(
    () => ({
      title: name,
      description,
      challenge_id: challengeId,
      round,
      label_config: project?.label_config ?? "<View></View>",
    }),
    [name, description, challengeId, round, project?.label_config],
  );

  const onCreate = React.useCallback(async () => {
    // First, persist project with label_config so import/reimport validates against it
    const response = await api.callApi("updateProject", {
      params: {
        pk: project.id,
      },
      body: projectBody,
    });

    if (response === null) return;

    const imported = await finishUpload();

    if (!imported) return;

    setWaitingStatus(true);

    if (sample) await uploadSample(sample);

    __lsa("create_project.create", { sample: sample?.url });

    setWaitingStatus(false);

    history.push(`/projects/${response.id}/data`);
  }, [project, projectBody, finishUpload]);

  const onSaveName = async () => {
    if (error) return;
    if (!project || !project.id) {
      setError("Project ID is missing. Cannot update project name.");
      return;
    }
    const res = await api.callApi("updateProjectRaw", {
      params: {
        pk: project.id,
      },
      body: {
        title: name,
      },
    });

    if (res.ok) return;
    const err = await res.json();

    setError(err.validation_errors?.title);
  };

  const onDelete = React.useCallback(() => {
    const performClose = async () => {
      setWaitingStatus(true);
      if (project)
        await api.callApi("deleteProject", {
          params: {
            pk: project.id,
          },
        });
      setWaitingStatus(false);
      updateProject(null);
      onClose?.();
    };
    performClose();
  }, [project]);

  return (
    <Modal onHide={onDelete} closeOnClickOutside={false} allowToInterceptEscape fullscreen visible bare>
      <div className={rootClass}>
        <Modal.Header>
          <h1>Create Project</h1>
          <ToggleItems items={steps} active={step} onSelect={setStep} />

          <Space>
            <Button
              variant="negative"
              look="outlined"
              size="small"
              onClick={onDelete}
              waiting={waiting}
              aria-label="Cancel project creation"
            >
              Cancel
            </Button>
            <Button
              look="primary"
              size="small"
              onClick={onCreate}
              waiting={waiting || uploading}
              disabled={!project || uploadDisabled || error}
              style={{ backgroundColor: "#EABE00", borderColor: "#EABE00" }}
            >
              Save
            </Button>
          </Space>
        </Modal.Header>
        <ProjectName
          name={name}
          setName={setName}
          error={error}
          onSaveName={onSaveName}
          onSubmit={onCreate}
          description={description}
          setDescription={setDescription}
          show={step === "name"}
          challengeId={challengeId}
          setChallengeId={setChallengeId}
          round={round}
          setRound={setRound}
          selectedChallenge={selectedChallenge}
          onChallengeSelect={handleChallengeSelect}
          challenges={challenges}
          challengesLoading={challengesLoading}
        />
        <ImportPage
          project={project}
          show={step === "import"}
          sample={sample}
          onSampleDatasetSelect={setSample}
          openLabelingConfig={() => setStep("config")}
          {...pageProps}
        />
        <ConfigPage
          project={project}
          onUpdate={(config) => {
            updateProject({ ...project, label_config: config });
          }}
          show={step === "config"}
          columns={columns}
          disableSaveButton={true}
        />
      </div>
    </Modal>
  );
};
