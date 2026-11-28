function make_model_figures(inputRoot, outputRoot)
%MAKE_MODEL_FIGURES Export reproducible Q3/Q4 paper figures from accepted v6 tables.
%   make_model_figures(INPUTROOT, OUTPUTROOT) takes implementation_v6 (or a
%   compatible replay) and writes vector PDF, 300 dpi PNG, and plotting data.
arguments
    inputRoot (1,1) string
    outputRoot (1,1) string
end
assert(isfolder(inputRoot), "The v6 result directory does not exist.")
if ~isfolder(outputRoot)
    mkdir(outputRoot);
end

p = palette();
thresholds = [15 60];
methods = ["historical_baseline", "direct_joint", "conditional_tree", "shared_five_leaf"];
selected = ["direct_joint" "conditional_tree"];
candidatePooled = loadTable(inputRoot, "joint_candidate/candidate_joint_pooled.csv", ["method" "scope"]);
candidateMonthly = loadTable(inputRoot, "joint_candidate/candidate_comparison.csv", ["period" "scope" "method" "test_row_hash" "candidate_test_row_hash"]);
assert(all(candidateMonthly.n == candidateMonthly.candidate_n & ...
    candidateMonthly.events == candidateMonthly.candidate_events & ...
    candidateMonthly.test_row_hash == candidateMonthly.candidate_test_row_hash), ...
    "Five-leaf comparison does not use the same scored rows and labels.")
requestedScope = "new_core_months";
periods = ["2024-09","2025-09","2026-09"];
brierPlot = table();
septemberPlot = table();
for t = 1:numel(thresholds)
    threshold = thresholds(t);
    folder = "primary_t"+threshold;
    pooled = loadTable(inputRoot, folder+"/joint_pooled_v5.csv", ["method" "scope"]);
    monthly = loadTable(inputRoot, folder+"/joint_monthly_v5.csv", ["period" "scope" "method"]);
    base = oneRow(pooled, pooled.scope == requestedScope & pooled.method == methods(1));
    for k = 1:numel(methods)
        method = methods(k);
        if method == "shared_five_leaf"
            ref = oneRow(candidatePooled, candidatePooled.scope == requestedScope & ...
                candidatePooled.threshold_minutes == threshold & candidatePooled.method == method);
            scores = candidateMonthly(candidateMonthly.scope == requestedScope & ...
                candidateMonthly.threshold_minutes == threshold & candidateMonthly.method == selected(t), :);
            losses = scores.candidate_brier;
            counts = scores.candidate_n;
        else
            ref = oneRow(pooled, pooled.scope == requestedScope & pooled.method == method);
            scores = monthly(monthly.scope == requestedScope & monthly.method == method, :);
            losses = scores.brier;
            counts = scores.n;
        end
        assert(ref.n == base.n && ref.events == base.events && ref.month_count == 15 && ...
            numel(counts) == 15 && sum(counts) == ref.n && ...
            abs(sum(losses.*counts)/sum(counts) - ref.pooled_brier) < 5e-13, ...
            "The pooled Brier score disagrees with the flight-weighted monthly scores.")
        brierPlot = [brierPlot; table(threshold, method, ref.n, ref.events, ref.pooled_brier, ...
            ref.pooled_brier-base.pooled_brier, method == selected(t), ...
            'VariableNames', ["threshold_minutes","method","n","events","brier", ...
            "brier_minus_baseline","selected_v5"])];
    end
    for j = 1:numel(periods)
        period = periods(j);
        row = oneRow(monthly, monthly.period == period & monthly.method == selected(t));
        assert(abs(row.events/row.n-row.observed) < 5e-13)
        septemberPlot = [septemberPlot; table(threshold, period, selected(t), row.n, ...
            row.events, row.observed, row.predicted, row.predicted-row.observed, ...
            'VariableNames', ["threshold_minutes","period","method","n","events", ...
            "observed","predicted","predicted_minus_observed"])];
    end
end
assert(isequal(septemberPlot.n(1:3),septemberPlot.n(4:6)), ...
    "The two thresholds must share the September denominators.")

events = loadTable(inputRoot, "primary_t60/external_event_scores.csv", ...
    ["event","window","method"]);
eventIDs = ["DL_CrowdStrike_20240719_23","MCO_Milton_EOC_Level_I_20241009_10"];
eventPlot = table();
for j = 1:numel(eventIDs)
    rows = events(events.event == eventIDs(j), :);
    event = rows(rows.window == "external_event", :);
    controls = rows(rows.window == "calendar_controls_not_verified_calm", :);
    assert(height(event)==3 && height(controls)==3, "Expected all three frozen methods per window.")
    assert(all(event.n == event.n(1) & event.events == event.events(1) & ...
        event.cancelled == event.cancelled(1)) && all(controls.n == controls.n(1) & ...
        controls.events == controls.events(1)), "Event denominators do not match across methods.")
    assert(all(abs(rows.observed-rows.events./rows.n) < 5e-13) && ...
        all(rows.predicted >= 0 & rows.predicted <= 1), "Invalid event risk.")
    series = ["event_observed";"controls_observed";methods(1:3)'];
    predicted = zeros(3,1);
    for k = 1:3
        row = oneRow(event, event.method == methods(k));
        predicted(k) = row.predicted;
    end
    rate = [event.observed(1);controls.observed(1);predicted];
    sample = [event.n(1);controls.n(1);repmat(event.n(1),3,1)];
    window = [event.window(1);controls.window(1);repmat(event.window(1),3,1)];
    eventPlot = [eventPlot; table(repmat(eventIDs(j),5,1),window,series,sample,rate, ...
        'VariableNames', ["event","window","series","n","rate"])];
end

fprintf('Input table checks passed. Exporting Brier comparison.\n');
plotBrier(brierPlot,p,outputRoot)
fprintf('Exporting September calibration comparison.\n');
plotSeptember(septemberPlot,p,outputRoot)
fprintf('Exporting external-event comparison.\n');
plotEvents(eventPlot,p,eventIDs,outputRoot)
writetable(brierPlot, fullfile(outputRoot,"q3_model_brier_values.csv"))
writetable(septemberPlot, fullfile(outputRoot,"q3_september_calibration_values.csv"))
writetable(eventPlot, fullfile(outputRoot,"q4_external_event_stress_values.csv"))
metadata = struct("matlab_version",version,"release",version("-release"), ...
    "inputs",["primary_t15/joint_pooled_v5.csv","primary_t60/joint_pooled_v5.csv", ...
    "primary_t15/joint_monthly_v5.csv","primary_t60/joint_monthly_v5.csv", ...
    "joint_candidate/candidate_joint_pooled.csv","joint_candidate/candidate_comparison.csv", ...
    "primary_t60/external_event_scores.csv"], ...
    "source_scope","Accepted v6 retrospective results; no extra selection or fitting.", ...
    "brier_months",15,"flights_in_brier_comparison",brierPlot.n(1));
[fileID,msg] = fopen(fullfile(outputRoot,"model_figures_matlab_run.json"),"w","n","UTF-8");
assert(fileID >= 0, msg)
cleanup = onCleanup(@() fclose(fileID));
fprintf(fileID,'%s\n',jsonencode(metadata,PrettyPrint=true));
fprintf('MATLAB %s exported three model figures to %s\n',version,outputRoot);
end

function data = loadTable(root, relativePath, stringFields)
path = fullfile(root, relativePath);
assert(isfile(path), "Required input is missing: %s", path)
options = detectImportOptions(path, TextType="string", VariableNamingRule="preserve");
options = setvartype(options, stringFields, "string");
data = readtable(path,options);
end

function row = oneRow(data, keep)
assert(nnz(keep)==1, "Expected exactly one row for the requested method and scope.")
row = data(keep,:);
end

function p = palette()
p.ink = [0.08 0.14 0.20];
p.neutral = [0.38 0.43 0.47];
p.grid = [0.85 0.88 0.91];
p.gray = [0.55 0.60 0.65];
p.blue = [0.08 0.36 0.64];
p.teal = [0.04 0.43 0.39];
p.amber = [0.70 0.35 0.12];
p.red = [0.60 0.19 0.29];
end

function plotBrier(scores,p,out)
fig = journalFigure(7.25,3.30);
cleanup = onCleanup(@() close(fig));
heading(fig, "Same-flight probability forecast scores", ...
    "15 core months used by the v5 model-selection rule | "+separateThousands(scores.n(1))+" flights", p)
paletteRows = [p.gray;p.blue;p.teal;p.amber];
labels = ["Historical baseline","Direct joint","Outcome tree","Shared five-leaf"];
for i = 1:2
    panel = [0.242+0.374*(i-1) 0.274 0.336 0.465];
    ax = panelAxes(fig,panel,p);
    t = [15 60]; t = t(i);
    rows = scores(scores.threshold_minutes == t,:);
    xlim(ax,[-5.25 1.70]);
    ylim(ax,[0.5 4.5]);
    ax.YDir = 'reverse';
    ax.XTick = -5:1;
    ax.YTick = 1:4;
    if i==1
        ax.YTickLabel = labels;
    else
        ax.YTickLabel = repmat("",1,4);
    end
    ax.TickLength = [0.012 0.012];
    ax.XGrid = 'on';
    ax.GridColor = p.grid;
    ax.GridAlpha = 0.70;
    ax.Layer = 'bottom';
    plot(ax,[0 0],[0.52 4.48],'--','Color',p.gray,'LineWidth',1.0)
    for k = 1:height(rows)
        x = 1e3*rows.brier_minus_baseline(k);
        c = paletteRows(k,:);
        plot(ax,[x 0],[k k],'-','Color',c,'LineWidth',1.15)
        marker = c;
        if rows.method(k) == "shared_five_leaf"
            marker = [1 1 1];
        end
        plot(ax,x,k,'o','Color',c,'MarkerFaceColor',marker,'MarkerSize',6,'LineWidth',1.35)
        weight = 'normal';
        if rows.selected_v5(k)
            weight = 'bold';
        end
        text(ax,x+0.15,k-0.16,sprintf('%.6f',rows.brier(k)), ...
            'FontName','Arial','FontSize',8.55,'Color',p.ink,'FontWeight',weight)
    end
    title(ax, sprintf('%c   %d-minute threshold','a'+i-1,t),'Color',p.ink, ...
        'FontName','Arial','FontSize',11,'FontWeight','bold')
    xlabel(ax,"Brier difference from baseline (\times 10^{-3})", ...
        'FontSize',8.9,'Color',p.ink,'Interpreter','tex')
end
footer(fig,["Negative differences indicate lower Brier scores. Labels give absolute scores; bold marks the v5 selection.", ...
    "The open marker denotes the shared five-leaf model, assessed retrospectively on the same flights."],p,0.055)
saveFigure(fig,out,"q3_model_brier")
end

function plotSeptember(scores,p,out)
fig = journalFigure(7.25,3.35);
cleanup = onCleanup(@() close(fig));
heading(fig,"Same-season calibration drift", ...
    "September cohorts from 2024 to 2026 | Models fitted through March 2024 and calibrated through June 2024", p)
displayMethod = ["Direct joint","Outcome tree"];
limits = [14 29;3 12.5];
ticks = {15:3:27,4:2:12};
colors = [p.blue;p.teal];
for i = 1:2
    panel = [0.132+0.472*(i-1) 0.272 0.347 0.472];
    ax = panelAxes(fig,panel,p);
    t = [15 60]; t = t(i);
    rows = scores(scores.threshold_minutes == t,:);
    x = 1:3;
    obs = 100*rows.observed';
    pred = 100*rows.predicted';
    c = colors(i,:);
    xlim(ax,[0.77 3.28]);
    ylim(ax,limits(i,:))
    ax.XTick = x;
    ax.XTickLabel = ["2024","2025","2026"];
    ax.YTick = ticks{i};
    ax.YGrid = 'on';
    ax.GridColor = p.grid;
    ax.GridAlpha = 0.75;
    ax.Layer = 'bottom';
    plot(ax,x,obs,'-o','Color',p.ink,'MarkerFaceColor',p.ink, ...
        'MarkerSize',5.3,'LineWidth',1.6)
    plot(ax,x,pred,'--s','Color',c,'MarkerFaceColor',[1 1 1], ...
        'MarkerSize',5.3,'LineWidth',1.35)
    for k = 1:3
        direction = sign(obs(k)-pred(k));
        ds = 0.36+0.16*(i==1);
        datalabel(ax,x(k),obs(k)+direction*ds,sprintf('%.1f',obs(k)),p.ink,direction)
        datalabel(ax,x(k),pred(k)-direction*ds,sprintf('%.1f',pred(k)),c,-direction)
    end
    title(ax,sprintf('%c   %d-minute threshold','a'+i-1,t),'Color',p.ink, ...
        'FontSize',11,'FontName','Arial','FontWeight','bold')
    xlabel(ax,displayMethod(i)+" forecast",'Color',c,'FontSize',9)
    ylabel(ax,"Joint failure rate (%)",'Color',p.ink,'FontSize',9)
end
foot = "Cohort sizes in date order: "+separateThousands(scores.n(1))+", " + ...
    separateThousands(scores.n(2))+", and "+separateThousands(scores.n(3))+" flights.";
footer(fig,["Solid circles: observed rate. Dashed squares: mean forecast. Vertical axes differ by panel.",foot],p,0.057)
saveFigure(fig,out,"q3_september_calibration")
end

function plotEvents(data,p,ids,out)
fig = journalFigure(7.25,3.65);
cleanup = onCleanup(@() close(fig));
heading(fig,"Routine forecasts underestimated both disruptions", ...
    "60-minute joint risk | Observed event rates and routine-model forecasts on the same flights",p)
labels = ["Observed event","Calendar control","Historical baseline","Direct joint","Outcome tree"];
subtitle = ["Delta outage","Orlando EOC activation"];
dates = ["19-23 Jul 2024","9-10 Oct 2024"];
paletteRows = [p.red;p.gray;p.gray;p.blue;p.teal];
for i=1:2
    panel = [0.246+0.376*(i-1) 0.259 0.325 0.449];
    ax = panelAxes(fig,panel,p);
    rows = data(data.event == ids(i),:);
    means = 100*rows.rate;
    xlim(ax,[0 114]);
    ylim(ax,[0.5 5.5]);
    ax.YDir = 'reverse';
    ax.XTick = [0 25 50 75 100];
    ax.YTick = 1:5;
    if i==1
        ax.YTickLabel = labels;
    else
        ax.YTickLabel = repmat("",1,5);
    end
    ax.XGrid = 'on';
    ax.GridColor = p.grid;
    ax.GridAlpha = 0.75;
    ax.Layer = 'bottom';
    for k = 1:height(rows)
        x = means(k);
        c = paletteRows(k,:);
        weight = 7.0;
        if k == 2
            weight = 4.0;
        end
        plot(ax,[0 x],[k k],'-','Color',c,'LineWidth',weight)
        text(ax,x+2,k,sprintf('%.1f',x),'FontName','Arial','FontSize',8.3, ...
            'Color',p.ink,'VerticalAlignment','middle')
    end
    titleLines = [string(sprintf('%c   %s','a'+i-1,subtitle(i))); ...
        dates(i)+" | event n = "+separateThousands(rows.n(1))];
    title(ax,cellstr(titleLines), ...
        'FontSize',9.5,'FontName','Arial','FontWeight','bold','Color',p.ink)
    xlabel(ax,"Joint failure rate (%)",'Color',p.ink,'FontSize',8.9)
end
footer(fig,["Joint failure includes cancellation, diversion, or arrival at least 60 minutes late.", ...
    "Calendar controls use neighboring dates on the same weekdays. Calm conditions and causal effects are unverified."],p,0.045)
saveFigure(fig,out,"q4_external_event_stress")
end

function fig = journalFigure(width,height)
fig = figure('Visible','off','Color','white','Units','inches', ...
    'Position',[1 1 width height],'InvertHardcopy','off','PaperUnits','inches');
fig.PaperPositionMode = 'manual';
fig.PaperPosition = [0 0 width height];
fig.PaperSize = [width height];
end

function ax = panelAxes(fig,position,p)
ax = axes(fig,'Units','normalized','Position',position,'NextPlot','add', ...
    'FontName','Arial','FontSize',9,'Box','off','Color','white','Layer','bottom', ...
    'XColor',p.neutral,'YColor',p.neutral,'LineWidth',0.75,'TickDir','out');
end

function heading(fig,titleText,subtitle,p)
addText(fig,[0.052 0.884 0.93 0.084],titleText,15,'bold',p.ink)
addText(fig,[0.052 0.802 0.93 0.079],subtitle,9,'normal',p.neutral)
end

function footer(fig,lines,p,y)
addText(fig,[0.052 y 0.94 0.105],lines,8.25,'normal',p.neutral)
end

function addText(fig,position,stringValue,fontSize,weight,color)
annotation(fig,'textbox',position,'String',cellstr(stringValue), ...
    'FontName','Arial','FontSize',fontSize,'FontWeight',weight,'BackgroundColor','none', ...
    'Color',color,'Interpreter','none','EdgeColor','none','Margin',0, ...
    'FitBoxToText','off','VerticalAlignment','middle');
end

function datalabel(ax,x,y,label,color,above)
alignment = 'top';
if above>0
    alignment = 'bottom';
end
text(ax,x,y,label,'FontName','Arial','FontSize',8.4,'Color',color, ...
    'HorizontalAlignment','center','VerticalAlignment',alignment)
end

function textValue = separateThousands(number)
groups = regexp(fliplr(sprintf('%d',number)),'.{1,3}','match');
textValue = string(fliplr(strjoin(groups,',')));
end

function saveFigure(fig,out,stem)
drawnow
print(fig, fullfile(out,stem+".pdf"), '-dpdf','-painters');
print(fig, fullfile(out,stem+".png"), '-dpng','-r300','-painters');
end

