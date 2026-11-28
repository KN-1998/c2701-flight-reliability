function render_v7_followup(resultsDir,outputDir)
% Render new C2701 analysis figures from audited v7 CSV outputs.
% MATLAB R2025a. Use explicit paths; no Statistics Toolbox required.
arguments
    resultsDir (1,1) string
    outputDir (1,1) string
end
if ~isfolder(outputDir), mkdir(outputDir); end
blue=[0.09 0.32 0.53]; orange=[0.72 0.28 0.10]; teal=[0.06 0.45 0.39];
grey=[0.28 0.30 0.34]; ink=[0.12 0.16 0.20];
monthly=load_csv(fullfile(resultsDir,"followup","followup_monthly.csv"));
pooled=load_csv(fullfile(resultsDir,"followup","followup_pooled.csv"));
blocks=load_csv(fullfile(resultsDir,"followup","followup_date_blocks.csv"));
figureHandle=paperFigure(17.8,12.8);
layout=tiledlayout(figureHandle,2,2,"TileSpacing","compact","Padding","compact");
for panel=1:2
    threshold=[15 60]; threshold=threshold(panel);
    reference=monthly(monthly.threshold_minutes==threshold & monthly.method=="historical_baseline",:);
    [period,order]=sort(reference.period);
    reference=reference(order,:);
    methods=["direct_joint","conditional_tree","shared_five_leaf"];
    colors=[blue;orange;teal];
    ax=nexttile(layout,panel); style(ax,ink); hold(ax,"on");
    yline(ax,0,":","Color",grey,"HandleVisibility","off");
    for k=1:3
        group=monthly(monthly.threshold_minutes==threshold & monthly.method==methods(k),:);
        [found,idx]=ismember(period,group.period);
        assert(all(found),"Missing matching follow-up month");
        plot(ax,1:numel(period),1000*(group.brier(idx)-reference.brier),"-o", ...
             "Color",colors(k,:),"LineWidth",1.15,"MarkerSize",3.8);
    end
    decorateMonth(ax,period,grey);
    title(ax,sprintf('(%s) %d-min Brier difference',char('a'+panel-1),threshold),"Color",ink);
    ylabel(ax,"Δ Brier × 1000","Color",ink);
    if panel==1
        leg=legend(ax,["Direct","Outcome tree","Shared five-leaf"],"Location","best","Box","off","FontSize",7);
        leg.TextColor=ink;
    end
    ax=nexttile(layout,panel+2); style(ax,ink); hold(ax,"on");
    selected="conditional_tree"; if threshold==15, selected="direct_joint"; end
    group=monthly(monthly.threshold_minutes==threshold & monthly.method==selected,:);
    [found,idx]=ismember(period,group.period);
    assert(all(found),"Missing selected model");
    plot(ax,1:numel(period),100*reference.observed,"-o","Color",grey,"LineWidth",1.2,"MarkerSize",4);
    plot(ax,1:numel(period),100*group.predicted(idx),"-s","Color",blue,"LineWidth",1.2,"MarkerSize",4);
    decorateMonth(ax,period,grey);
    title(ax,sprintf('(%s) %d-min average risk',char('a'+panel+1),threshold),"Color",ink);
    ylabel(ax,"Risk (%)","Color",ink);
    if panel==1
        leg=legend(ax,["Observed","Frozen selected forecast"],"Location","best","Box","off","FontSize",7);
        leg.TextColor=ink;
    end
end
writeFigure(figureHandle,outputDir,"fig07_frozen_followup");
writetable(pooled,fullfile(outputDir,"table_v7_followup_pooled.csv"));
writetable(blocks,fullfile(outputDir,"table_v7_followup_date_blocks.csv"));

taf=load_csv(fullfile(resultsDir,"weather","taf_pooled.csv"));
diffs=load_csv(fullfile(resultsDir,"weather","taf_date_blocks.csv"));
stress=load_csv(fullfile(resultsDir,"weather","taf_stress_pooled.csv"));
exposure=load_csv(fullfile(resultsDir,"weather","taf_stress_date_blocks.csv"));
figureHandle=paperFigure(17.8,8.9);
layout=tiledlayout(figureHandle,1,2,"TileSpacing","compact","Padding","compact");
ax=nexttile(layout); style(ax,ink); hold(ax,"on");
w=diffs(diffs.block_days==7,:);
[~,idx]=sort(w.threshold_minutes);
w=w(idx,:);
assert(height(w)==2,"Expected a seven-day interval at each threshold");
yline(ax,0,":","Color",grey,"HandleVisibility","off");
errorbar(ax,1:2,1000*w.estimate,1000*(w.estimate-w.low),1000*(w.high-w.estimate),"o", ...
         "Color",blue,"MarkerFaceColor",blue,"LineWidth",1.2,"CapSize",8);
xlim(ax,[0.5 2.5]); ax.XTick=1:2; ax.XTickLabel={'15 min','60 min'};
title(ax,"(a) Archived TAF versus schedule proxy","Color",ink);
ylabel(ax,"Δ Brier × 1000 (TAF minus proxy)","Color",ink);

ax=nexttile(layout); style(ax,ink); hold(ax,"on");
labels=["adverse_forecast","no_adverse_signal","holiday_proxy_window","other_calendar_days"];
selected=stress(stress.scope=="frozen_followup" & stress.threshold_minutes==60 & ...
                stress.method=="schedule_plus_origin_taf",:);
[found,idx]=ismember(labels,selected.group);
assert(all(found),"Missing a time-defined subgroup");
values=selected(idx,:);
b=bar(ax,[100*values.observed,100*values.predicted],"grouped");
b(1).FaceColor=grey; b(2).FaceColor=teal;
b(1).EdgeColor="none"; b(2).EdgeColor="none";
ax.XTick=1:4;
ax.XTickLabel={'Adverse TAF','No adverse signal','Holiday ±1 day','Other dates'};
xtickangle(ax,25);
title(ax,"(b) 60-min stress groups","Color",ink);
ylabel(ax,"Risk (%)","Color",ink);
leg=legend(ax,["Observed","TAF model"],"Location","best","FontSize",7,"Box","off");
leg.TextColor=ink;
writeFigure(figureHandle,outputDir,"fig08_predeparture_taf");
writetable(taf,fullfile(outputDir,"table_v7_taf_pooled.csv"));
writetable(stress,fullfile(outputDir,"table_v7_taf_stress.csv"));
writetable(exposure,fullfile(outputDir,"table_v7_taf_stress_date_blocks.csv"));

groups=load_csv(fullfile(resultsDir,"airport_groups","stricter_support_pooled.csv"));
writetable(groups,fullfile(outputDir,"table_v7_coverage_by_stratification.csv"));
fprintf("C2701 v7 figures generated with MATLAB %s\n",version);
end

function data=load_csv(path)
opts=detectImportOptions(path,"TextType","string","VariableNamingRule","preserve");
asText=intersect(["period","scope","method","contrast","group","role","stratification"], string(opts.VariableNames));
if ~isempty(asText), opts=setvartype(opts,asText,"string"); end
data=readtable(path,opts);
end

function f=paperFigure(w,h)
f=figure("Visible","off","Color",[1 1 1],"Units","centimeters", ...
         "Position",[2 2 w h],"PaperPositionMode","auto","Renderer","painters");
end

function style(ax,ink)
ax.Color=[1 1 1]; ax.XColor=ink; ax.YColor=ink;
ax.FontName="Arial"; ax.FontSize=8; ax.LineWidth=.65; ax.TickDir="out";
ax.GridColor=[.75 .78 .81]; ax.GridAlpha=.45; ax.YGrid="on";
ax.Box="off";
end

function decorateMonth(ax,period,grey)
labels=extractAfter(period,5);
ax.XTick=1:numel(period); ax.XTickLabel=labels;
xlim(ax,[.72 numel(period)+.28]); xlabel(ax,"2026 month");
xline(ax,8.5,":","Color",grey,"HandleVisibility","off");
end

function writeFigure(f,directory,base)
exportgraphics(f,fullfile(directory,base+".pdf"),"ContentType","vector","BackgroundColor","white");
exportgraphics(f,fullfile(directory,base+".png"),"Resolution",600,"BackgroundColor","white");
close(f);
end

