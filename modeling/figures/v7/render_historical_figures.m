function render_historical_figures(resultsDir, outputDir)
%RENDER_HISTORICAL_FIGURES Render C2701 Q1, Q2, and Q5 from verified V6 tables.
%   render_historical_figures(ROOT, OUTPUT) reads modeling/results/implementation_v6.
%   It produces vector PDF and 320 dpi PNG for each figure. All rates derive
%   from past reported scheduled segments. No model is fit by this script.

arguments
    resultsDir (1,1) string
    outputDir (1,1) string
end
assert(isfolder(resultsDir), 'C2701:ResultsMissing', 'Results directory is missing.');
if ~isfolder(outputDir)
    mkdir(outputDir);
end

thresholdFigure(resultsDir, outputDir);
compositionFigure(resultsDir, outputDir);
travelerFigure(resultsDir, outputDir);
fprintf('MATLAB %s (%s): completed three historical figures.\n', version, version('-release'));
end


function thresholdFigure(resultsDir, outputDir)
file = fullfile(resultsDir, 'historical_airport_scorecard.csv');
data = readTextTable(file, "Origin");
thresholds = [0 15 30 60 120];
vars = "reliability_" + string(thresholds) + "_lower";
assert(all(ismember(vars, string(data.Properties.VariableNames))) && height(data) == 10 ...
    && all(data.n > 0), 'C2701:Q1Input', 'Ten valid historical airport rows are required.');
[~, order] = sort(data.reliability_15_lower, 'descend');
data = data(order,:);
names = data.Origin;
rates = 100 * data{:, cellstr(vars)};
assert(all(isfinite(rates), 'all') && all(diff(rates,1,2) >= -1e-10, 'all'), ...
    'C2701:Q1Monotonicity', 'Historical strict reliability must increase with threshold.');

fig = newFigure(11.8, 5.28);
t = tiledlayout(fig, 1, 2, 'TileSpacing','compact', 'Padding','compact');
title(t, 'Reliability changes with the threshold and denominator', ...
    'FontWeight','bold', 'FontSize',15, 'Color',ink());

ax = nexttile(t);
styleAxes(ax);
hold(ax, 'on');
light = [0.94 0.97 0.99];
dark = [0.17 0.37 0.53];
for i = 1:height(data)
    for j = 1:length(thresholds)
        v = rates(i,j);
        amount = max(0,min(1,(v-50)/50));
        fill = light + amount * (dark-light);
        patch(ax, j+[-0.49 0.49 0.49 -0.49], i+[-0.48 -0.48 0.48 0.48], fill, ...
            'EdgeColor','none');
        textColor = ink();
        if dot(fill, [0.2126 0.7152 0.0722]) < 0.51
            textColor = [1 1 1];
        end
        text(ax, j, i, sprintf('%.1f',v), 'FontSize',9, 'FontName','Arial', ...
            'FontWeight','bold', 'Color',textColor, 'HorizontalAlignment','center');
    end
end
set(ax, 'YDir','reverse', 'YTick',1:10, 'YTickLabel',cellstr(names), ...
    'XTick',1:5, 'XTickLabel',cellstr(string(thresholds)), 'TickLength',[0 0]);
xlim(ax,[.5 5.5]); ylim(ax,[.5 10.5]);
xlabel(ax,'Exclusive arrival-delay threshold (minutes)');
title(ax,'A  Strict success per planned segment (%)', 'FontSize',11,'Color',ink(),'FontWeight','bold');

ax = nexttile(t);
styleAxes(ax);
hold(ax,'on');
scheduled = 100*data.reliability_15_lower;
conditional = 100*data.conditional_on_time;
for i=1:height(data)
    plot(ax,[scheduled(i) conditional(i)],[i i],'-','Color',[.67 .72 .76],'LineWidth',1.25);
end
a = scatter(ax, scheduled, 1:10, 42, 'o','filled','MarkerFaceColor',blue());
b = scatter(ax, conditional, 1:10, 47, 'd','filled','MarkerFaceColor',orange());
set(ax,'YDir','reverse','YTick',1:10,'YTickLabel',cellstr(names));
ylim(ax,[.5 10.5]);
xlim(ax,[floor(min(scheduled))-1 ceil(max(conditional))+1]);
grid(ax,'on'); ax.YGrid='off';
xlabel(ax,'At 15 minutes (%)');
title(ax,'B  Same threshold, different denominator', 'FontSize',11,'Color',ink(),'FontWeight','bold');
legend(ax,[a b],{'Per planned segment','Given normal completion'},'Location','southoutside', ...
    'Orientation','horizontal','Box','off','FontSize',9,'TextColor',ink());
exportFigure(fig, outputDir, "fig01_reliability_definitions");
end


function compositionFigure(resultsDir, outputDir)
dirName = fullfile(resultsDir, 'comparison_2023_2025');
support = readTextTable(fullfile(dirName,'common_support_coverage.csv'),"airport");
pairs = readTextTable(fullfile(dirName,'pairwise_comparisons.csv'),["a","b","mode"]);
assert(height(support)==10 && all(support.coverage>=0 & support.coverage<=1), ...
    'C2701:Q2Input','Expected ten valid airport coverage rows.');
share = 100*sum(support.supported_n)/sum(support.total_n);
modes = ["raw","raw_common_support","standardized"];
airports = ["ATL","SEA"];
colors = [blue(); orange()];
marks = {'o','d'};

fig = newFigure(11.8, 5.0);
t = tiledlayout(fig, 1, 2, 'TileSpacing','compact','Padding','compact');
title(t, 'Restricting support and reweighting can change airport comparisons', ...
    'FontSize',15,'FontWeight','bold','Color',ink());

ax = nexttile(t);
styleAxes(ax);
hold(ax,'on');
yline(ax, 0, ':', 'Color',[.39 .44 .48],'LineWidth',1.1);
handles = gobjects(1,2);
limits = [];
for i=1:2
    rows = pairs([],:);
    for j=1:numel(modes)
        match = oneRow(pairs, pairs.a == airports(i) & pairs.b == "SFO" & pairs.mode == modes(j) & ...
            pairs.threshold_minutes == 15 & pairs.block_days == 7);
        rows = [rows; match]; %#ok<AGROW>
    end
    x = (1:3) + (i-1.5)*0.14;
    point = 100*rows.difference;
    lo = 100*rows.ci_lower;
    hi = 100*rows.ci_upper;
    whiskers(ax, x, lo, hi, colors(i,:), .04);
    handles(i) = plot(ax,x,point,['-' marks{i}],'Color',colors(i,:), ...
        'LineWidth',1.5,'MarkerFaceColor',colors(i,:), 'MarkerSize',6);
    limits = [limits; point; lo; hi]; %#ok<AGROW>
end
set(ax, 'XTick',1:3,'XTickLabel',{'All planned','Shared cells','Standardized'});
xlim(ax,[.7 3.3]);
ylim(ax,[min(limits,[],'omitnan')-.35, max(limits,[],'omitnan')+.45]);
ylabel(ax,'Airport minus SFO (percentage points)');
xlabel(ax,'Comparison population and weighting');
title(ax,'A  Difference in 15-minute strict success', 'FontSize',11,'Color',ink(),'FontWeight','bold');
legend(ax,handles,{'ATL minus SFO','SEA minus SFO'},'Location','southoutside', ...
    'Orientation','horizontal','Box','off','FontSize',9,'TextColor',ink());
grid(ax,'on'); ax.XGrid='off';

ax = nexttile(t);
styleAxes(ax);
hold(ax,'on');
[~,order] = sort(support.coverage,'descend');
support = support(order,:);
bars = barh(ax,1:10,100*support.coverage,0.62,'FaceColor','flat','EdgeColor','none');
bars.CData = repmat([.47 .64 .75],10,1);
highlight = ismember(support.airport, ["ATL","SEA","SFO"]);
bars.CData(highlight,:) = repmat(blue(),sum(highlight),1);
xline(ax,share,':','Color',[.27 .32 .36],'LineWidth',1.1);
for i=1:height(support)
    text(ax,100*support.coverage(i)+1.15,i,sprintf('%.1f',100*support.coverage(i)), ...
        'FontName','Arial','FontSize',9,'Color',ink());
end
set(ax, 'YDir','reverse','YTick',1:10,'YTickLabel',cellstr(support.airport));
xlim(ax,[0 107]); ylim(ax,[.5 10.5]);
xticks(ax,0:25:100);
xlabel(ax,'Shared-support fraction (%)');
title(ax,sprintf('B  Pooled coverage is %.2f%%',share), 'FontSize',11,'Color',ink(),'FontWeight','bold');
grid(ax,'on'); ax.YGrid='off';
exportFigure(fig,outputDir,"fig02_airport_composition");
end


function travelerFigure(resultsDir,outputDir)
dirName = fullfile(resultsDir,'traveler_card');
card = readTextTable(fullfile(dirName,'matched_comparisons.csv'),["period","target","reference_scope"]);
support = readTextTable(fullfile(dirName,'support_coverage.csv'),["period","airport","reference_scope"]);
pooled = oneRow(support,support.period=="2023-2025" & support.airport=="EWR");
pooledLga = oneRow(support,support.period=="2023-2025" & support.airport=="LGA");
targets = ["cancellation","diversion","long_delay_60_per_scheduled", ...
    "long_delay_60_given_completed","joint_bad_60"];
labels = {'Cancellation','Diversion','Delay 60+ (per planned)', ...
    'Delay 60+ (per completion)','60-minute joint risk'};

fig = newFigure(11.8, 4.68);
t = tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');
title(t,'Traveler priorities distinguish EWR and LGA in shared cells to DEN', ...
    'FontSize',15,'FontWeight','bold','Color',ink());
ax = nexttile(t);
styleAxes(ax);
hold(ax,'on');
adjusted = zeros(5,2);
for i=1:numel(targets)
    row = oneRow(card,card.period=="2023-2025" & card.target==targets(i) & card.block_days==7);
    adjusted(i,:) = 100*[row.EWR_adjusted_rate,row.LGA_adjusted_rate];
    plot(ax,adjusted(i,:),[i i],'-','Color',[.66 .71 .75],'LineWidth',1.3);
end
a = scatter(ax,adjusted(:,1),1:5,54,'o','filled','MarkerFaceColor',blue());
b = scatter(ax,adjusted(:,2),1:5,54,'d','filled','MarkerFaceColor',orange());
set(ax,'YDir','reverse','YTick',1:5,'YTickLabel',labels);
ylim(ax,[0.5 5.5]);
xlim(ax,[0 ceil(max(adjusted,[],'all'))+.7]);
xlabel(ax,'Adjusted historical risk (%)');
grid(ax,'on'); ax.YGrid='off';
title(ax,sprintf('A  Pooled coverage: EWR %.1f%%, LGA %.1f%%', ...
    100*pooled.coverage,100*pooledLga.coverage),'FontSize',11,'Color',ink(),'FontWeight','bold');
legend(ax,[a b],{'EWR to DEN','LGA to DEN'},'Location','southoutside', ...
    'Orientation','horizontal','Box','off','FontSize',9,'TextColor',ink());

ax = nexttile(t);
styleAxes(ax);
hold(ax,'on');
yr = 2023:2025;
keys = ["cancellation","long_delay_60_per_scheduled"];
colors = [blue();orange()];
marks = {'o','d'};
handles = gobjects(1,2);
yline(ax,0,':','Color',[.39 .44 .48],'LineWidth',1.1);
for i=1:2
    values = zeros(3,3);
    for j=1:3
        row = oneRow(card,card.period==string(yr(j)) & card.target==keys(i) & card.block_days==7);
        assert(row.reference_scope=="fixed_cross_year_common_support", ...
            'C2701:Q5Scope','The annual panel requires a fixed cross-year reference.');
        values(j,:) = 100*[row.adjusted_difference,row.experimental_95_low,row.experimental_95_high];
    end
    x = yr+(i-1.5)*0.17;
    whiskers(ax,x,values(:,2),values(:,3),colors(i,:),.038);
    handles(i)=plot(ax,x,values(:,1),marks{i},'MarkerFaceColor',colors(i,:), ...
        'MarkerEdgeColor',colors(i,:),'MarkerSize',6);
end
xlim(ax,[2022.64 2025.36]); xticks(ax,yr);
xlabel(ax,'Year');
ylabel(ax,'EWR minus LGA (percentage points)');
title(ax,'B  Annual differences on fixed shared cells', 'FontSize',11,'Color',ink(),'FontWeight','bold');
legend(ax,handles,{'Cancellation','Delay 60+ per planned'},'Location','southoutside', ...
    'Orientation','horizontal','Box','off','FontSize',9,'TextColor',ink());
grid(ax,'on'); ax.XGrid='off';
exportFigure(fig,outputDir,"fig03_traveler_scorecard");
end


function data = readTextTable(path, names)
assert(isfile(path),'C2701:InputMissing','Missing data file: %s',path);
opts = detectImportOptions(path,'VariableNamingRule','preserve');
opts = setvartype(opts,cellstr(names),'string');
data = readtable(path, opts);
end


function row = oneRow(data, mask)
row = data(mask,:);
assert(height(row)==1,'C2701:InputKey','Each figure input key must identify one row.');
end


function fig = newFigure(w,h)
fig = figure('Visible','off','Color','white','Units','inches', ...
    'Position',[.5 .5 w h], 'Renderer','painters');
end


function styleAxes(ax)
set(ax,'Color','white','FontName','Arial','FontSize',10,'LineWidth',.7, ...
    'XColor',ink(),'YColor',ink(),'Box','off','TickDir','out', ...
    'GridColor',[.65 .69 .73],'GridAlpha',.35,'Layer','top');
end


function whiskers(ax, x, lo, hi, color, cap)
for i=1:numel(x)
    if isfinite(lo(i)) && isfinite(hi(i))
        line(ax,[x(i) x(i)],[lo(i) hi(i)],'Color',color,'LineWidth',1.08);
        line(ax,x(i)+[-cap cap],[lo(i) lo(i)],'Color',color,'LineWidth',1.08);
        line(ax,x(i)+[-cap cap],[hi(i) hi(i)],'Color',color,'LineWidth',1.08);
    end
end
end


function exportFigure(fig, outputDir, stem)
drawnow;
exportgraphics(fig,fullfile(outputDir,stem+".pdf"),'ContentType','vector','BackgroundColor','white','Units','inches','Padding',0.075);
exportgraphics(fig,fullfile(outputDir,stem+".png"),'Resolution',320,'BackgroundColor','white','Units','inches','Padding',0.075);
close(fig);
end


function color = ink()
color = [0.13 0.19 0.24];
end


function color = blue()
color = [0.04 0.34 0.55];
end


function color = orange()
color = [0.76 0.31 0.09];
end




