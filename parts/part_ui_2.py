"""ClipCard, CustomClipDialog, ViralCopyPackDialog, ClipStudioScreen, ClipPulseApp, Application, and MainActivity."""

FILES = {
    "app/src/main/java/com/clippulse/app/ui/studio/ClipStudioDialogs.kt": r'''
package com.clippulse.app.ui.studio

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.ui.theme.ClipPulseShapes
import com.clippulse.app.ui.theme.MonoTimestampStyle
import com.clippulse.app.util.UrlNormalizer
import java.util.Locale

@Composable
fun CustomClipDialog(
    durationSec: Double,
    onDismiss: () -> Unit,
    onCreate: (title: String, startSec: Double, endSec: Double) -> Unit
) {
    var title by remember { mutableStateOf("Custom Highlight") }
    var startText by remember { mutableStateOf("0") }
    var endText by remember { mutableStateOf(String.format(Locale.US, "%.0f", minOf(30.0, durationSec))) }
    var errorMsg by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = ClipPulseColors.Slate,
        titleContentColor = ClipPulseColors.TextPrimary,
        textContentColor = ClipPulseColors.TextPrimary,
        title = { Text("Create Custom Clip", style = MaterialTheme.typography.titleLarge) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "Video length: ${UrlNormalizer.formatTimestamp(durationSec)} (${durationSec.toInt()}s). Enter seconds or mm:ss.",
                    style = MaterialTheme.typography.bodySmall
                )
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Clip Title") },
                    singleLine = true,
                    shape = ClipPulseShapes.Chip,
                    colors = dialogFieldColors(),
                    modifier = Modifier.fillMaxWidth()
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    OutlinedTextField(
                        value = startText,
                        onValueChange = {
                            startText = it
                            errorMsg = null
                        },
                        label = { Text("Start (s / mm:ss)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                        shape = ClipPulseShapes.Chip,
                        colors = dialogFieldColors(),
                        modifier = Modifier.weight(1f)
                    )
                    OutlinedTextField(
                        value = endText,
                        onValueChange = {
                            endText = it
                            errorMsg = null
                        },
                        label = { Text("End (s / mm:ss)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                        shape = ClipPulseShapes.Chip,
                        colors = dialogFieldColors(),
                        modifier = Modifier.weight(1f)
                    )
                }
                errorMsg?.let { err ->
                    Text(
                        text = err,
                        color = ClipPulseColors.CrimsonHeatmap,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val s = parseFlexibleTime(startText)
                    val e = parseFlexibleTime(endText)
                    if (s == null || e == null || e <= s + 1.0) {
                        errorMsg = "Enter valid start/end times with end greater than start."
                    } else {
                        onCreate(title, s.coerceIn(0.0, durationSec), e.coerceIn(0.0, durationSec))
                    }
                },
                shape = ClipPulseShapes.Chip,
                colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.Indigo),
                modifier = Modifier.height(48.dp)
            ) {
                Text("Add Clip")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.height(48.dp)
            ) {
                Text("Cancel", color = ClipPulseColors.TextSecondary)
            }
        }
    )
}

@Composable
fun ViralCopyPackDialog(
    clip: ClipCandidate,
    isLoading: Boolean,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val pack = clip.copyPack

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = ClipPulseColors.Slate,
        titleContentColor = ClipPulseColors.TextPrimary,
        textContentColor = ClipPulseColors.TextPrimary,
        title = {
            Column {
                Text("Viral Copy Pack", style = MaterialTheme.typography.titleLarge)
                Text(
                    text = "${clip.title} • ${UrlNormalizer.formatTimestamp(clip.startSec)}-${UrlNormalizer.formatTimestamp(clip.endSec)}",
                    style = MonoTimestampStyle,
                    color = ClipPulseColors.CyanAiPick
                )
            }
        },
        text = {
            if (isLoading || pack == null) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 20.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    CircularProgressIndicator(
                        color = ClipPulseColors.CyanAiPick,
                        modifier = Modifier.size(22.dp),
                        strokeWidth = 2.dp
                    )
                    Spacer(Modifier.width(12.dp))
                    Text("Drafting titles, hook & tags...", style = MaterialTheme.typography.bodyMedium)
                }
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    CopySection(label = "3-Second Hook", body = pack.hook)
                    CopySection(
                        label = "Title Ideas",
                        body = pack.titles.mapIndexed { i, t -> "${i + 1}. $t" }.joinToString("\n")
                    )
                    CopySection(label = "Description", body = pack.description)
                    CopySection(label = "Hashtags", body = pack.hashtags.joinToString(" "))
                }
            }
        },
        confirmButton = {
            if (pack != null && !isLoading) {
                Button(
                    onClick = {
                        val fullText = buildString {
                            appendLine(pack.titles.firstOrNull().orEmpty())
                            appendLine()
                            appendLine("Hook: ${pack.hook}")
                            appendLine()
                            appendLine(pack.description)
                            appendLine()
                            appendLine(pack.hashtags.joinToString(" "))
                        }
                        copyToClipboard(context, "Viral Copy Pack", fullText)
                    },
                    shape = ClipPulseShapes.Chip,
                    colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.Indigo),
                    modifier = Modifier.height(48.dp)
                ) {
                    Icon(Icons.Default.ContentCopy, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Copy All")
                }
            }
        },
        dismissButton = {
            OutlinedButton(
                onClick = onDismiss,
                shape = ClipPulseShapes.Chip,
                border = BorderStroke(1.dp, ClipPulseColors.Hairline),
                modifier = Modifier.height(48.dp)
            ) {
                Text("Close")
            }
        }
    )
}

@Composable
private fun CopySection(label: String, body: String) {
    Surface(
        shape = ClipPulseShapes.Chip,
        color = ClipPulseColors.Elevated,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelMedium,
                color = ClipPulseColors.CyanAiPick
            )
            Text(
                text = body,
                style = MaterialTheme.typography.bodySmall,
                color = ClipPulseColors.TextPrimary
            )
        }
    }
}

private fun parseFlexibleTime(raw: String): Double? {
    val trimmed = raw.trim()
    if (trimmed.isEmpty()) return null
    if (!trimmed.contains(':')) {
        return trimmed.toDoubleOrNull()
    }
    val parts = trimmed.split(':').map { it.toDoubleOrNull() ?: return null }
    return when (parts.size) {
        2 -> parts[0] * 60.0 + parts[1]
        3 -> parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
        else -> null
    }
}

private fun copyToClipboard(context: Context, label: String, text: String) {
    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    cm.setPrimaryClip(ClipData.newPlainText(label, text))
    Toast.makeText(context, "Copied to clipboard", Toast.LENGTH_SHORT).show()
}

@Composable
private fun dialogFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = ClipPulseColors.Indigo,
    unfocusedBorderColor = ClipPulseColors.Hairline,
    focusedContainerColor = ClipPulseColors.Obsidian,
    unfocusedContainerColor = ClipPulseColors.Obsidian,
    focusedTextColor = ClipPulseColors.TextPrimary,
    unfocusedTextColor = ClipPulseColors.TextPrimary
)
''',

    "app/src/main/java/com/clippulse/app/ui/studio/ClipStudioScreen.kt": r'''
package com.clippulse.app.ui.studio

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Cookie
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Update
import androidx.compose.material.icons.filled.VideoFile
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.SignalType
import com.clippulse.app.service.ExportForegroundService
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.ui.theme.ClipPulseShapes
import com.clippulse.app.ui.theme.MonoTimestampStyle
import com.clippulse.app.ui.theme.signalColor
import com.clippulse.app.util.UrlNormalizer
import com.clippulse.app.viewmodel.StudioViewModel
import okhttp3.OkHttpClient
import java.util.Locale

@Composable
fun ClipStudioScreen(
    viewModel: StudioViewModel,
    okHttpClient: OkHttpClient,
    onExportStarted: () -> Unit
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current

    val localVideoPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            runCatching {
                context.contentResolver.takePersistableUriPermission(
                    uri,
                    android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
            }
            viewModel.startScan(uri.toString())
        }
    }

    val cookiesPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            viewModel.importCookies(uri)
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            ScanInputCard(
                urlInput = state.urlInput,
                isScanning = state.isScanning,
                scanStage = state.scanStage,
                cookiesImported = state.cookiesImported,
                isUpdatingEngine = state.isUpdatingEngine,
                onUrlChange = viewModel::updateUrlInput,
                onScanClick = { viewModel.startScan() },
                onCancelClick = viewModel::cancelScan,
                onPickLocalVideo = { localVideoPicker.launch(arrayOf("video/*")) },
                onImportCookies = { cookiesPicker.launch(arrayOf("text/plain", "*/*")) },
                onClearCookies = viewModel::clearCookies,
                onUpdateEngine = viewModel::updateYtDlpEngine
            )
        }

        state.scanError?.let { err ->
            item {
                MessageBanner(
                    text = err,
                    accent = ClipPulseColors.CrimsonHeatmap,
                    onDismiss = viewModel::dismissBanner
                )
            }
        }

        state.statusBanner?.let { info ->
            item {
                MessageBanner(
                    text = info,
                    accent = ClipPulseColors.EmeraldAudio,
                    onDismiss = viewModel::dismissBanner
                )
            }
        }

        state.activeExport?.takeIf { it.isRunning }?.let { active ->
            item {
                Surface(
                    shape = ClipPulseShapes.Card,
                    color = ClipPulseColors.Elevated,
                    border = BorderStroke(1.dp, ClipPulseColors.Indigo),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = "Exporting: ${active.clipTitle}",
                                style = MaterialTheme.typography.titleSmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f)
                            )
                            Text(
                                text = String.format(Locale.US, "%d%%", (active.progress * 100f).toInt()),
                                style = MonoTimestampStyle,
                                color = ClipPulseColors.Indigo
                            )
                        }
                        Text(text = active.stage, style = MaterialTheme.typography.bodySmall)
                        LinearProgressIndicator(
                            progress = { active.progress.coerceIn(0f, 1f) },
                            color = ClipPulseColors.Indigo,
                            trackColor = ClipPulseColors.Obsidian,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(5.dp)
                        )
                    }
                }
            }
        }

        val metadata = state.metadata
        if (metadata != null) {
            item {
                VideoHeaderCard(
                    title = metadata.title,
                    uploader = metadata.uploader,
                    durationSec = metadata.durationSec,
                    clientUsed = state.clientUsed,
                    superChatCount = metadata.superChats.size,
                    onAddCustomClip = { viewModel.openCustomClipDialog(true) }
                )
            }

            item {
                HeatmapTimeline(
                    durationSec = metadata.durationSec,
                    heatmap = metadata.heatmap,
                    superChats = metadata.superChats,
                    clips = state.clips,
                    selectedClipId = state.selectedClip?.id,
                    onSelectClip = viewModel::selectClip
                )
            }

            state.selectedClip?.let { activeClip ->
                item {
                    PreviewPlayerCard(
                        metadata = metadata,
                        clip = activeClip,
                        okHttpClient = okHttpClient,
                        onTrimChanged = { s, e -> viewModel.updateClipTrim(activeClip.id, s, e) },
                        onNudgeStart = { delta -> viewModel.nudgeClipStart(activeClip.id, delta) },
                        onNudgeEnd = { delta -> viewModel.nudgeClipEnd(activeClip.id, delta) },
                        onExportClick = { viewModel.openExportSheet(activeClip) }
                    )
                }
            }

            item {
                SignalFilterBar(
                    selectedFilter = state.selectedFilter,
                    totalCount = state.clips.size,
                    onSelectFilter = viewModel::selectFilter
                )
            }

            items(state.filteredClips, key = { it.id }) { clip ->
                ClipCard(
                    clip = clip,
                    isSelected = clip.id == state.selectedClip?.id,
                    onSelect = { viewModel.selectClip(clip.id) },
                    onCopyPack = { viewModel.openCopyPack(clip) },
                    onExport = { viewModel.openExportSheet(clip) }
                )
            }
        } else if (!state.isScanning) {
            item {
                EmptyStudioHintCard()
            }
        }
    }

    if (state.showCustomClipDialog && state.metadata != null) {
        CustomClipDialog(
            durationSec = state.metadata!!.durationSec,
            onDismiss = { viewModel.openCustomClipDialog(false) },
            onCreate = { title, startSec, endSec ->
                viewModel.addCustomClip(title, startSec, endSec)
            }
        )
    }

    state.copyPackClip?.let { clip ->
        ViralCopyPackDialog(
            clip = clip,
            isLoading = state.isGeneratingCopyPack,
            onDismiss = viewModel::dismissCopyPack
        )
    }

    val exportTarget = state.exportTargetClip
    val currentMeta = state.metadata
    if (exportTarget != null && currentMeta != null) {
        ExportOptionsSheet(
            clip = exportTarget,
            metadata = currentMeta,
            onDismiss = { viewModel.openExportSheet(null) },
            onStartExport = { config ->
                viewModel.openExportSheet(null)
                ExportForegroundService.startExport(context, config)
                onExportStarted()
            }
        )
    }
}

@Composable
private fun ScanInputCard(
    urlInput: String,
    isScanning: Boolean,
    scanStage: String,
    cookiesImported: Boolean,
    isUpdatingEngine: Boolean,
    onUrlChange: (String) -> Unit,
    onScanClick: () -> Unit,
    onCancelClick: () -> Unit,
    onPickLocalVideo: () -> Unit,
    onImportCookies: () -> Unit,
    onClearCookies: () -> Unit,
    onUpdateEngine: () -> Unit
) {
    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Slate,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            OutlinedTextField(
                value = urlInput,
                onValueChange = onUrlChange,
                placeholder = { Text("Paste YouTube, Live VOD, or Facebook URL...") },
                singleLine = true,
                enabled = !isScanning,
                trailingIcon = {
                    if (urlInput.isNotEmpty() && !isScanning) {
                        IconButton(
                            onClick = { onUrlChange("") },
                            modifier = Modifier.size(48.dp)
                        ) {
                            Icon(
                                Icons.Default.Close,
                                contentDescription = "Clear URL",
                                tint = ClipPulseColors.TextMuted
                            )
                        }
                    }
                },
                shape = ClipPulseShapes.Chip,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = ClipPulseColors.Indigo,
                    unfocusedBorderColor = ClipPulseColors.Hairline,
                    focusedContainerColor = ClipPulseColors.Obsidian,
                    unfocusedContainerColor = ClipPulseColors.Obsidian,
                    focusedTextColor = ClipPulseColors.TextPrimary,
                    unfocusedTextColor = ClipPulseColors.TextPrimary
                ),
                modifier = Modifier.fillMaxWidth()
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = if (isScanning) onCancelClick else onScanClick,
                    shape = ClipPulseShapes.Chip,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isScanning) ClipPulseColors.CrimsonHeatmap else ClipPulseColors.Indigo
                    ),
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                ) {
                    if (isScanning) {
                        Icon(Icons.Default.Stop, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Stop Scan")
                    } else {
                        Icon(Icons.Default.Search, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Zero-DL Scan", fontWeight = FontWeight.SemiBold)
                    }
                }

                OutlinedButton(
                    onClick = onPickLocalVideo,
                    enabled = !isScanning,
                    shape = ClipPulseShapes.Chip,
                    border = BorderStroke(1.dp, ClipPulseColors.Hairline),
                    modifier = Modifier.height(48.dp)
                ) {
                    Icon(Icons.Default.VideoFile, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Local")
                }
            }

            AnimatedVisibility(
                visible = isScanning,
                enter = fadeIn(tween(180)),
                exit = fadeOut(tween(180))
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        text = scanStage.ifBlank { "Scanning..." },
                        style = MaterialTheme.typography.bodySmall,
                        color = ClipPulseColors.CyanAiPick
                    )
                    LinearProgressIndicator(
                        color = ClipPulseColors.Indigo,
                        trackColor = ClipPulseColors.Obsidian,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(4.dp)
                    )
                }
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                FilterChip(
                    selected = cookiesImported,
                    onClick = { if (cookiesImported) onClearCookies() else onImportCookies() },
                    leadingIcon = {
                        Icon(
                            Icons.Default.Cookie,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                    },
                    label = { Text(if (cookiesImported) "Cookies Active (Tap to Clear)" else "Import cookies.txt") },
                    shape = ClipPulseShapes.Chip,
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = ClipPulseColors.EmeraldAudio.copy(alpha = 0.16f),
                        selectedLabelColor = ClipPulseColors.EmeraldAudio,
                        selectedLeadingIconColor = ClipPulseColors.EmeraldAudio,
                        containerColor = ClipPulseColors.Elevated,
                        labelColor = ClipPulseColors.TextSecondary
                    ),
                    border = FilterChipDefaults.filterChipBorder(
                        enabled = true,
                        selected = cookiesImported,
                        borderColor = ClipPulseColors.Hairline,
                        selectedBorderColor = ClipPulseColors.EmeraldAudio
                    )
                )

                FilterChip(
                    selected = isUpdatingEngine,
                    onClick = { if (!isUpdatingEngine) onUpdateEngine() },
                    leadingIcon = {
                        if (isUpdatingEngine) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(14.dp),
                                strokeWidth = 2.dp,
                                color = ClipPulseColors.CyanAiPick
                            )
                        } else {
                            Icon(Icons.Default.Update, contentDescription = null, modifier = Modifier.size(16.dp))
                        }
                    },
                    label = { Text(if (isUpdatingEngine) "Updating yt-dlp..." else "Update Engine") },
                    shape = ClipPulseShapes.Chip,
                    colors = FilterChipDefaults.filterChipColors(
                        containerColor = ClipPulseColors.Elevated,
                        labelColor = ClipPulseColors.TextSecondary,
                        selectedContainerColor = ClipPulseColors.Elevated,
                        selectedLabelColor = ClipPulseColors.CyanAiPick
                    ),
                    border = FilterChipDefaults.filterChipBorder(
                        enabled = true,
                        selected = isUpdatingEngine,
                        borderColor = ClipPulseColors.Hairline,
                        selectedBorderColor = ClipPulseColors.CyanAiPick
                    )
                )
            }
        }
    }
}

@Composable
private fun VideoHeaderCard(
    title: String,
    uploader: String,
    durationSec: Double,
    clientUsed: String,
    superChatCount: Int,
    onAddCustomClip: () -> Unit
) {
    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Slate,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(end = 10.dp),
                verticalArrangement = Arrangement.spacedBy(3.dp)
            ) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = "$uploader • ${UrlNormalizer.formatTimestamp(durationSec)} • $clientUsed" +
                        if (superChatCount > 0) " • $superChatCount Super Chats" else "",
                    style = MonoTimestampStyle,
                    color = ClipPulseColors.TextSecondary,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            OutlinedButton(
                onClick = onAddCustomClip,
                shape = ClipPulseShapes.Chip,
                border = BorderStroke(1.dp, ClipPulseColors.CyanAiPick),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp),
                modifier = Modifier.height(48.dp)
            ) {
                Icon(
                    Icons.Default.Add,
                    contentDescription = null,
                    tint = ClipPulseColors.CyanAiPick,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(Modifier.width(4.dp))
                Text("Custom", color = ClipPulseColors.CyanAiPick)
            }
        }
    }
}

@Composable
private fun SignalFilterBar(
    selectedFilter: SignalType?,
    totalCount: Int,
    onSelectFilter: (SignalType?) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        FilterChip(
            selected = selectedFilter == null,
            onClick = { onSelectFilter(null) },
            label = { Text("All ($totalCount)") },
            shape = ClipPulseShapes.Chip,
            colors = FilterChipDefaults.filterChipColors(
                selectedContainerColor = ClipPulseColors.Indigo,
                selectedLabelColor = Color.White,
                containerColor = ClipPulseColors.Slate,
                labelColor = ClipPulseColors.TextSecondary
            ),
            border = FilterChipDefaults.filterChipBorder(
                enabled = true,
                selected = selectedFilter == null,
                borderColor = ClipPulseColors.Hairline,
                selectedBorderColor = ClipPulseColors.Indigo
            )
        )
        SignalType.entries.forEach { type ->
            val selected = selectedFilter == type
            val color = signalColor(type)
            FilterChip(
                selected = selected,
                onClick = { onSelectFilter(type) },
                label = { Text(type.label) },
                shape = ClipPulseShapes.Chip,
                colors = FilterChipDefaults.filterChipColors(
                    selectedContainerColor = color.copy(alpha = 0.22f),
                    selectedLabelColor = color,
                    containerColor = ClipPulseColors.Slate,
                    labelColor = ClipPulseColors.TextSecondary
                ),
                border = FilterChipDefaults.filterChipBorder(
                    enabled = true,
                    selected = selected,
                    borderColor = ClipPulseColors.Hairline,
                    selectedBorderColor = color
                )
            )
        }
    }
}

@Composable
private fun ClipCard(
    clip: ClipCandidate,
    isSelected: Boolean,
    onSelect: () -> Unit,
    onCopyPack: () -> Unit,
    onExport: () -> Unit
) {
    val accent = signalColor(clip.primarySignal)
    val borderColor = if (isSelected) accent else ClipPulseColors.Hairline

    Surface(
        shape = ClipPulseShapes.Card,
        color = if (isSelected) ClipPulseColors.Elevated else ClipPulseColors.Slate,
        border = BorderStroke(if (isSelected) 1.5.dp else 1.dp, borderColor),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onSelect)
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    clip.signals.take(3).forEach { sig ->
                        val sigCol = signalColor(sig)
                        Text(
                            text = sig.label,
                            color = sigCol,
                            style = MaterialTheme.typography.labelMedium,
                            modifier = Modifier
                                .background(sigCol.copy(alpha = 0.14f), ClipPulseShapes.Pill)
                                .border(1.dp, sigCol.copy(alpha = 0.45f), ClipPulseShapes.Pill)
                                .padding(horizontal = 8.dp, vertical = 3.dp)
                        )
                    }
                }
                Text(
                    text = String.format(Locale.US, "%d%%", (clip.score * 100.0).toInt()),
                    style = MonoTimestampStyle,
                    color = accent,
                    fontWeight = FontWeight.Bold
                )
            }

            Text(
                text = clip.title,
                style = MaterialTheme.typography.titleSmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            Text(
                text = String.format(
                    Locale.US,
                    "%s → %s  (%.1fs)",
                    UrlNormalizer.formatTimestamp(clip.startSec),
                    UrlNormalizer.formatTimestamp(clip.endSec),
                    clip.durationSec
                ),
                style = MonoTimestampStyle,
                color = ClipPulseColors.TextPrimary
            )

            Text(
                text = clip.reason,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            clip.superChat?.let { sc ->
                Surface(
                    shape = ClipPulseShapes.Chip,
                    color = ClipPulseColors.GoldSuperChat.copy(alpha = 0.12f),
                    border = BorderStroke(1.dp, ClipPulseColors.GoldSuperChat.copy(alpha = 0.45f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = "${sc.author} • ${sc.amountText}: ${sc.message}",
                        style = MaterialTheme.typography.bodySmall,
                        color = ClipPulseColors.GoldSuperChat,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(10.dp)
                    )
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(
                    onClick = onCopyPack,
                    shape = ClipPulseShapes.Chip,
                    border = BorderStroke(1.dp, ClipPulseColors.Hairline),
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                ) {
                    Icon(
                        Icons.Default.AutoAwesome,
                        contentDescription = null,
                        tint = ClipPulseColors.CyanAiPick,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.width(6.dp))
                    Text("Copy Pack")
                }

                Button(
                    onClick = onExport,
                    shape = ClipPulseShapes.Chip,
                    colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.Indigo),
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                ) {
                    Icon(Icons.Default.Download, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Export")
                }
            }
        }
    }
}

@Composable
private fun MessageBanner(
    text: String,
    accent: Color,
    onDismiss: () -> Unit
) {
    Surface(
        shape = ClipPulseShapes.Chip,
        color = accent.copy(alpha = 0.14f),
        border = BorderStroke(1.dp, accent.copy(alpha = 0.45f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = text,
                color = accent,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.weight(1f)
            )
            IconButton(onClick = onDismiss, modifier = Modifier.size(48.dp)) {
                Icon(Icons.Default.Close, contentDescription = "Dismiss", tint = accent)
            }
        }
    }
}

@Composable
private fun EmptyStudioHintCard() {
    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Slate,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                text = "Zero-Download Clip Studio",
                style = MaterialTheme.typography.titleMedium
            )
            Text(
                text = "Paste a YouTube video, livestream VOD, or Facebook URL — or pick a local video — to detect Most Replayed heatmap peaks, EN/HI/BN speech excitement, Super Chats, chat velocity spikes, and AI viral hooks without downloading the full video.",
                style = MaterialTheme.typography.bodySmall
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.horizontalScroll(rememberScrollState())
            ) {
                SignalType.entries.forEach { sig ->
                    val c = signalColor(sig)
                    Text(
                        text = sig.label,
                        color = c,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier
                            .background(c.copy(alpha = 0.14f), ClipPulseShapes.Pill)
                            .border(1.dp, c.copy(alpha = 0.4f), ClipPulseShapes.Pill)
                            .padding(horizontal = 10.dp, vertical = 4.dp)
                    )
                }
            }
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/ui/ClipPulseApp.kt": r'''
package com.clippulse.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.clippulse.app.AppContainer
import com.clippulse.app.ui.ai.AiManagerBottomSheet
import com.clippulse.app.ui.ai.AiStatusPill
import com.clippulse.app.ui.downloads.DownloadsScreen
import com.clippulse.app.ui.studio.ClipStudioScreen
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.viewmodel.AiSettingsViewModel
import com.clippulse.app.viewmodel.DownloadsViewModel
import com.clippulse.app.viewmodel.StudioViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ClipPulseApp(
    container: AppContainer,
    sharedUrl: String?,
    onSharedUrlConsumed: () -> Unit
) {
    val studioViewModel: StudioViewModel = viewModel(
        factory = StudioViewModel.Factory(
            scanRepository = container.scanRepository,
            prefsRepo = container.prefsRepo,
            exportProgressFlow = container.exportProgress
        )
    )
    val downloadsViewModel: DownloadsViewModel = viewModel(
        factory = DownloadsViewModel.Factory(
            prefsRepo = container.prefsRepo,
            storageManager = container.storageManager,
            historyRepository = container.historyRepository,
            exportProgressFlow = container.exportProgress
        )
    )
    val aiSettingsViewModel: AiSettingsViewModel = viewModel(
        factory = AiSettingsViewModel.Factory(
            prefsRepo = container.prefsRepo,
            aiClient = container.aiClient
        )
    )

    val aiConfig by container.prefsRepo.aiConfig.collectAsStateWithLifecycle()
    val exportProgress by container.exportProgress.collectAsStateWithLifecycle()

    var selectedTab by rememberSaveable { mutableIntStateOf(0) }
    var showAiSheet by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(sharedUrl) {
        if (!sharedUrl.isNullOrBlank()) {
            selectedTab = 0
            studioViewModel.startScan(sharedUrl)
            onSharedUrlConsumed()
        }
    }

    Scaffold(
        containerColor = ClipPulseColors.Obsidian,
        topBar = {
            Box {
                TopAppBar(
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = ClipPulseColors.Obsidian,
                        titleContentColor = ClipPulseColors.TextPrimary
                    ),
                    title = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.Movie,
                                contentDescription = null,
                                tint = ClipPulseColors.Indigo,
                                modifier = Modifier.size(22.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = "ClipPulse",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    },
                    actions = {
                        Box(modifier = Modifier.padding(end = 12.dp)) {
                            AiStatusPill(
                                offlineMode = aiConfig.offlineMode,
                                isConnected = aiConfig.isConnected,
                                model = aiConfig.lastConnectedModel,
                                onClick = { showAiSheet = true }
                            )
                        }
                    }
                )
                HorizontalDivider(
                    color = ClipPulseColors.Hairline,
                    thickness = 1.dp,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                )
            }
        },
        bottomBar = {
            Box {
                HorizontalDivider(
                    color = ClipPulseColors.Hairline,
                    thickness = 1.dp,
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .fillMaxWidth()
                )
                NavigationBar(
                    containerColor = ClipPulseColors.Slate,
                    tonalElevation = 0.dp,
                    modifier = Modifier.height(68.dp)
                ) {
                    NavigationBarItem(
                        selected = selectedTab == 0,
                        onClick = { selectedTab = 0 },
                        icon = { Icon(Icons.Default.ContentCut, contentDescription = "Studio") },
                        label = { Text("Studio") },
                        colors = navBarItemColors()
                    )
                    NavigationBarItem(
                        selected = selectedTab == 1,
                        onClick = { selectedTab = 1 },
                        icon = { Icon(Icons.Default.Download, contentDescription = "Downloads") },
                        label = {
                            Text(
                                if (exportProgress?.isRunning == true) "Downloads •" else "Downloads"
                            )
                        },
                        colors = navBarItemColors()
                    )
                }
            }
        }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(ClipPulseColors.Obsidian)
                .padding(innerPadding)
        ) {
            if (selectedTab == 0) {
                ClipStudioScreen(
                    viewModel = studioViewModel,
                    okHttpClient = container.okHttpClient,
                    onExportStarted = { selectedTab = 1 }
                )
            } else {
                DownloadsScreen(
                    viewModel = downloadsViewModel,
                    onRescanUrl = { url ->
                        selectedTab = 0
                        studioViewModel.startScan(url)
                    }
                )
            }
        }
    }

    if (showAiSheet) {
        AiManagerBottomSheet(
            viewModel = aiSettingsViewModel,
            onDismiss = { showAiSheet = false }
        )
    }
}

@Composable
private fun navBarItemColors() = NavigationBarItemDefaults.colors(
    selectedIconColor = ClipPulseColors.Indigo,
    selectedTextColor = ClipPulseColors.Indigo,
    indicatorColor = ClipPulseColors.Indigo.copy(alpha = 0.16f),
    unselectedIconColor = ClipPulseColors.TextSecondary,
    unselectedTextColor = ClipPulseColors.TextSecondary
)
''',

    "app/src/main/java/com/clippulse/app/ClipPulseApplication.kt": r'''
package com.clippulse.app

import android.app.Application

class ClipPulseApplication : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
''',

    "app/src/main/java/com/clippulse/app/MainActivity.kt": r'''
package com.clippulse.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import com.clippulse.app.ui.ClipPulseApp
import com.clippulse.app.ui.theme.ClipPulseTheme

class MainActivity : ComponentActivity() {

    private var pendingSharedUrl by mutableStateOf<String?>(null)

    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        handleIncomingIntent(intent)

        val appContainer = (application as ClipPulseApplication).container

        setContent {
            ClipPulseTheme {
                ClipPulseApp(
                    container = appContainer,
                    sharedUrl = pendingSharedUrl,
                    onSharedUrlConsumed = { pendingSharedUrl = null }
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIncomingIntent(intent)
    }

    private fun handleIncomingIntent(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            val shared = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()
            if (!shared.isNullOrBlank()) {
                pendingSharedUrl = shared
            }
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }
}
''',
}
