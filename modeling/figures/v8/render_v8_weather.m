function render_v8_weather(resultsDir,outputDir)
% Appendix illustration of the C2701 v8 retrospective weather comparison.
% From the repository root:
%   addpath("modeling/figures/v8")
%   render_v8_weather("modeling/results/v8_20261128","modeling/figures/v8")
% MATLAB R2025a. Panel (a) gives exploratory paired date-block ranges.

arguments
    resultsDir (1,1) string
    outputDir (1,1) string
end

binaryDir = fullfile(resultsDir,"corrected_binary");
sharedDir = fullfile(resultsDir,"joint");
impact = loadCsv(fullfile(binaryDir,"taf_source_impact_pooled.csv"));
blocks = loadCsv(fullfile(binaryDir,"taf_source_impact_date_blocks.csv"));
binaryStress = loadCsv(fullfile(binaryDir,"taf_stress_pooled.csv"));
sharedStress = loadCsv(fullfile(sharedDir,"shared_weather_stress_pooled.csv"));
binaryScores = loadCsv(fullfile(binaryDir,"taf_pooled.csv"));
sharedScores = loadCsv(fullfile(sharedDir,"shared_weather_pooled.csv"));
binaryRun = jsondecode(fileread(fullfile(binaryDir,"study_status.json")));
sharedRun = jsondecode(fileread(fullfile(sharedDir,"shared_weather_status.json")));
assert(strcmp(binaryRun.weather.normalized_taf_sha256,sharedRun.input_sha256.taf_segments) && ...
    sharedRun.reference_counts_and_identity_checked, ...
    "Weather scores do not attest to common source inputs and flight identities");

thresholds = [15;60];
history = "retrospective_2026_jan_aug";
sharedMethod = "shared_schedule_plus_origin_taf";
impact = selectThresholds(impact(impact.scope=="retrospective_jan_aug",:),thresholds);
blocks = selectThresholds(blocks(blocks.block_days==7 & ...
    blocks.contrast=="revised_taf_minus_original_taf",:),thresholds);
assert(isequal(impact.n,blocks.n) && all(abs(impact.brier_change-blocks.estimate)<1e-10) && ...
    all(isfinite(blocks.low) & isfinite(blocks.high) & blocks.low<=blocks.high), ...
    "Source correction and paired block tables disagree");

binary = binaryStress(binaryStress.scope=="frozen_followup" & ...
    binaryStress.threshold_minutes==60 & binaryStress.group=="adverse_forecast" & ...
    binaryStress.method=="schedule_plus_origin_taf",:);
shared = sharedStress(sharedStress.scope==history & ...
    sharedStress.threshold_minutes==60 & sharedStress.group=="adverse_forecast" & ...
    sharedStress.method==sharedMethod,:);
assert(height(binary)==1 && height(shared)==1 && binary.n==shared.n && ...
    binary.events==shared.events && abs(binary.observed-shared.observed)<1e-10, ...
    "Adverse weather cohorts are not comparable");

binaryScores = binaryScores(binaryScores.scope=="frozen_followup",:);
reference = selectThresholds(binaryScores(binaryScores.method=="schedule_proxy_only",:),thresholds);
revised = selectThresholds(binaryScores(binaryScores.method=="schedule_plus_origin_taf",:),thresholds);
joint = selectThresholds(sharedScores(sharedScores.scope==history & sharedScores.method==sharedMethod,:),thresholds);
assert(isequal(revised.n,reference.n,joint.n,impact.n) && ...
    isequal(revised.events,reference.events,joint.events) && ...
    all(abs(revised.brier-impact.brier_revised)<1e-10), ...
    "Source correction and model scores disagree");
brier = [impact.brier_original,revised.brier,joint.brier];

ink = [.12 .16 .20];
slate = [.44 .49 .55];
observedColor = [.25 .27 .31];
blue = [.08 .34 .58];
teal = [.04 .44 .38];
labels = ["15 min","60 min"];
colors = [slate;blue;teal];
f = figure("Visible","off","Color","white","Units","centimeters", ...
    "Position",[2 2 17.8 13],"Renderer","painters");
layout = tiledlayout(f,2,2,"TileSpacing","compact","Padding","compact");
title(layout,"Retrospective weather comparison, January–August 2026", ...
    "FontName","Arial","FontSize",10,"Color",ink);

ax = nexttile(layout,1);
paperAxis(ax,ink);
hold(ax,"on");
yline(ax,0,":","Color",slate,"LineWidth",.85);
scale = 1e6;
for index = 1:numel(thresholds)
    ends = scale * [blocks.low(index),blocks.high(index)];
    plot(ax,[index index],ends,"-","Color",blue,"LineWidth",1.15);
    for limit = ends
        plot(ax,index+[-.07 .07],[limit limit],"-","Color",blue,"LineWidth",1.15);
    end
end
plot(ax,1:2,scale*impact.brier_change,"o","Color",blue, ...
    "MarkerFaceColor",blue,"MarkerSize",4.8);
xlim(ax,[.5 2.5]);
ax.XTick = 1:2;
ax.XTickLabel = labels;
title(ax,"(a) TAF source correction","Color",ink);
ylabel(ax,"Brier change × 10^{6}");
xlabel(ax,"Revised − original, paired 7-day ranges");

ax = nexttile(layout,2);
paperAxis(ax,ink);
hold(ax,"on");
rates = 100*[binary.observed,binary.predicted,shared.predicted];
bars = bar(ax,rates,.6,"FaceColor","flat","EdgeColor","none");
bars.CData = [observedColor;blue;teal];
ylim(ax,[0 max(rates)*1.21]);
xlim(ax,[.45 3.55]);
ax.XTick = 1:3;
ax.XTickLabel = ["Observed","Revised binary","Shared five-leaf"];
xtickangle(ax,0);
for index = 1:numel(rates)
    text(ax,index,rates(index),sprintf("%.1f",rates(index)), ...
        "HorizontalAlignment","center","VerticalAlignment","bottom", ...
        "FontName","Arial","FontSize",8,"Color",ink);
end
title(ax,"(b) 60-min risk with adverse TAF","Color",ink);
ylabel(ax,"Risk (%)");

ax = nexttile(layout,3,[1 2]);
paperAxis(ax,ink);
hold(ax,"on");
delta = 1000*(brier-reference.brier);
series = bar(ax,delta,"grouped","EdgeColor","none");
for index = 1:numel(series)
    series(index).FaceColor = colors(index,:);
end
ax.XTick = 1:2;
ax.XTickLabel = labels;
title(ax,"(c) Brier difference from the schedule-only binary baseline","Color",ink);
ylabel(ax,"Brier difference × 10^{3}");
legend(ax,series,["Original binary TAF","Revised binary TAF","Shared five-leaf TAF"], ...
    "Location","southoutside","Orientation","horizontal","Box","off","FontSize",8,"TextColor",ink);

if ~isfolder(outputDir)
    mkdir(outputDir);
end
name = fullfile(outputDir,"fig09_taf_source_and_coherence");
exportgraphics(f,name+".pdf","ContentType","vector","BackgroundColor","white");
exportgraphics(f,name+".png","Resolution",600,"BackgroundColor","white");
close(f);
fprintf("C2701 v8 weather appendix generated with MATLAB %s\n",version);
end

function data = loadCsv(path)
options = detectImportOptions(path,"TextType","string","VariableNamingRule","preserve");
textColumns = intersect(["scope","method","contrast","group"],string(options.VariableNames));
options = setvartype(options,textColumns,"string");
data = readtable(path,options);
end

function subset = selectThresholds(subset,thresholds)
subset = sortrows(subset,"threshold_minutes");
assert(isequal(subset.threshold_minutes,thresholds), ...
    "Expected exactly one row per required threshold");
end

function paperAxis(ax,ink)
ax.FontName = "Arial";
ax.FontSize = 8;
ax.Color = "white";
ax.XColor = ink;
ax.YColor = ink;
ax.TickDir = "out";
ax.LineWidth = .65;
ax.YGrid = "on";
ax.GridColor = [.74 .77 .80];
ax.GridAlpha = .45;
ax.Box = "off";
end
