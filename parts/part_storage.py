"""MediaStore & SAF StorageManager, HistoryRepository, DownloadsViewModel, and DownloadsScreen."""

FILES = {
    "app/src/main/java/com/clippulse/app/data/storage/StorageManager.kt": r'''
package com.clippulse.app.data.storage

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import androidx.documentfile.provider.DocumentFile
import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.StoragePreset
import com.clippulse.app.util.ErrorSanitizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.nio.charset.StandardCharsets

data class SavedMediaFile(
    val contentUri: String,
    val sizeBytes: Long
)

class StorageManager(
    private val appContext: Context,
    private val prefsRepo: PrefsRepo
) {

    fun takePersistableSafPermission(treeUri: Uri): AppResult<String> {
        return try {
            val flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            appContext.contentResolver.takePersistableUriPermission(treeUri, flags)
            prefsRepo.setSafTreeUri(treeUri.toString())
            prefsRepo.setStoragePreset(StoragePreset.CUSTOM_SAF)
            AppResult.Success(treeUri.toString())
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Could not persist folder permission."), cause = e)
        }
    }

    suspend fun saveExportedClip(sourceFile: File, fileName: String): AppResult<SavedMediaFile> =
        withContext(Dispatchers.IO) {
            val preset = prefsRepo.storagePreset.value
            val safUriStr = prefsRepo.safTreeUri.value

            if (preset == StoragePreset.CUSTOM_SAF && safUriStr.isNotBlank()) {
                val safRes = saveToSaf(Uri.parse(safUriStr), sourceFile, fileName, "video/mp4")
                if (safRes is AppResult.Success) return@withContext safRes
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                saveToMediaStoreQPlus(sourceFile, fileName, preset)
            } else {
                saveToLegacyStorage(sourceFile, fileName, preset)
            }
        }

    suspend fun saveSidecarText(fileName: String, content: String): AppResult<String> =
        withContext(Dispatchers.IO) {
            val preset = prefsRepo.storagePreset.value
            val safUriStr = prefsRepo.safTreeUri.value

            if (preset == StoragePreset.CUSTOM_SAF && safUriStr.isNotBlank()) {
                val res = saveBytesToSaf(
                    Uri.parse(safUriStr),
                    fileName,
                    "text/plain",
                    content.toByteArray(StandardCharsets.UTF_8)
                )
                if (res is AppResult.Success) return@withContext res
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                try {
                    val values = ContentValues().apply {
                        put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                        put(MediaStore.Downloads.MIME_TYPE, "text/plain")
                        put(MediaStore.Downloads.RELATIVE_PATH, "Download/ClipPulse")
                        put(MediaStore.Downloads.IS_PENDING, 1)
                    }
                    val resolver = appContext.contentResolver
                    val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                        ?: return@withContext AppResult.Error("Could not create sidecar TXT in Downloads.")
                    resolver.openOutputStream(uri)?.use { out ->
                        out.write(content.toByteArray(StandardCharsets.UTF_8))
                    }
                    values.clear()
                    values.put(MediaStore.Downloads.IS_PENDING, 0)
                    resolver.update(uri, values, null, null)
                    AppResult.Success(uri.toString())
                } catch (e: Exception) {
                    saveSidecarFallbackFile(fileName, content)
                }
            } else {
                saveSidecarFallbackFile(fileName, content)
            }
        }

    private fun saveSidecarFallbackFile(fileName: String, content: String): AppResult<String> {
        return try {
            val dir = File(appContext.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS) ?: appContext.filesDir, "ClipPulse")
            dir.mkdirs()
            val outFile = File(dir, fileName)
            outFile.writeText(content, StandardCharsets.UTF_8)
            val uri = FileProvider.getUriForFile(appContext, "${appContext.packageName}.fileprovider", outFile)
            AppResult.Success(uri.toString())
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Failed to save sidecar TXT."))
        }
    }

    private fun saveToMediaStoreQPlus(
        sourceFile: File,
        fileName: String,
        preset: StoragePreset
    ): AppResult<SavedMediaFile> {
        return try {
            val resolver = appContext.contentResolver
            val relPath = preset.relativePath.ifBlank { StoragePreset.MOVIES_CLIPPULSE.relativePath }
            val collection = if (preset == StoragePreset.DOWNLOADS_CLIPPULSE && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                MediaStore.Downloads.EXTERNAL_CONTENT_URI
            } else {
                MediaStore.Video.Media.EXTERNAL_CONTENT_URI
            }
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                put(MediaStore.MediaColumns.MIME_TYPE, "video/mp4")
                put(MediaStore.MediaColumns.RELATIVE_PATH, relPath)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val uri = resolver.insert(collection, values)
                ?: return AppResult.Error("MediaStore declined clip insertion.")

            resolver.openOutputStream(uri)?.use { out ->
                FileInputStream(sourceFile).use { input ->
                    input.copyTo(out)
                }
            } ?: return AppResult.Error("Could not open MediaStore output stream.")

            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            AppResult.Success(SavedMediaFile(uri.toString(), sourceFile.length()))
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Failed to save video to MediaStore."), cause = e)
        }
    }

    @Suppress("DEPRECATION")
    private fun saveToLegacyStorage(
        sourceFile: File,
        fileName: String,
        preset: StoragePreset
    ): AppResult<SavedMediaFile> {
        return try {
            val publicType = when (preset) {
                StoragePreset.DOWNLOADS_CLIPPULSE -> Environment.DIRECTORY_DOWNLOADS
                StoragePreset.DCIM_CLIPPULSE -> Environment.DIRECTORY_DCIM
                else -> Environment.DIRECTORY_MOVIES
            }
            val publicDir = File(Environment.getExternalStoragePublicDirectory(publicType), "ClipPulse")
            val targetDir = if (publicDir.exists() || publicDir.mkdirs()) {
                publicDir
            } else {
                File(appContext.getExternalFilesDir(Environment.DIRECTORY_MOVIES) ?: appContext.filesDir, "ClipPulse").apply {
                    mkdirs()
                }
            }
            val outFile = File(targetDir, fileName)
            FileInputStream(sourceFile).use { input ->
                FileOutputStream(outFile).use { output ->
                    input.copyTo(output)
                }
            }
            val uri = FileProvider.getUriForFile(appContext, "${appContext.packageName}.fileprovider", outFile)
            AppResult.Success(SavedMediaFile(uri.toString(), outFile.length()))
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Failed to save video on legacy storage."), cause = e)
        }
    }

    private fun saveToSaf(
        treeUri: Uri,
        sourceFile: File,
        fileName: String,
        mimeType: String
    ): AppResult<SavedMediaFile> {
        return try {
            val docTree = DocumentFile.fromTreeUri(appContext, treeUri)
                ?: return AppResult.Error("Selected SAF folder is no longer accessible.")
            val created = docTree.createFile(mimeType, fileName)
                ?: return AppResult.Error("Could not create file in custom SAF folder.")
            appContext.contentResolver.openOutputStream(created.uri)?.use { out ->
                FileInputStream(sourceFile).use { input ->
                    input.copyTo(out)
                }
            } ?: return AppResult.Error("Could not open SAF output stream.")
            AppResult.Success(SavedMediaFile(created.uri.toString(), sourceFile.length()))
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "SAF export failed."), cause = e)
        }
    }

    private fun saveBytesToSaf(
        treeUri: Uri,
        fileName: String,
        mimeType: String,
        bytes: ByteArray
    ): AppResult<String> {
        return try {
            val docTree = DocumentFile.fromTreeUri(appContext, treeUri)
                ?: return AppResult.Error("SAF folder unavailable.")
            val created = docTree.createFile(mimeType, fileName)
                ?: return AppResult.Error("Could not create sidecar TXT in SAF folder.")
            appContext.contentResolver.openOutputStream(created.uri)?.use { out ->
                out.write(bytes)
            }
            AppResult.Success(created.uri.toString())
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Failed to write sidecar TXT to SAF."))
        }
    }

    fun deleteMediaUri(uriString: String) {
        runCatching {
            val uri = Uri.parse(uriString)
            appContext.contentResolver.delete(uri, null, null)
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/storage/HistoryRepository.kt": r'''
package com.clippulse.app.data.storage

import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.domain.model.ExportRecord
import com.clippulse.app.domain.model.ScanHistoryItem
import kotlinx.coroutines.flow.StateFlow

class HistoryRepository(private val prefsRepo: PrefsRepo) {

    val scanHistory: StateFlow<List<ScanHistoryItem>> = prefsRepo.scanHistory
    val exportHistory: StateFlow<List<ExportRecord>> = prefsRepo.exportHistory

    fun recordExport(record: ExportRecord) {
        prefsRepo.addExportRecord(record)
    }

    fun removeExport(id: String) {
        prefsRepo.removeExportRecord(id)
    }

    fun removeScan(id: String) {
        prefsRepo.removeScanHistory(id)
    }
}
''',

    "app/src/main/java/com/clippulse/app/viewmodel/DownloadsViewModel.kt": r'''
package com.clippulse.app.viewmodel

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.data.storage.HistoryRepository
import com.clippulse.app.data.storage.StorageManager
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.ExportProgress
import com.clippulse.app.domain.model.ExportRecord
import com.clippulse.app.domain.model.ScanHistoryItem
import com.clippulse.app.domain.model.StoragePreset
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class DownloadsUiState(
    val storagePreset: StoragePreset = StoragePreset.MOVIES_CLIPPULSE,
    val safTreeUri: String = "",
    val exports: List<ExportRecord> = emptyList(),
    val scanHistory: List<ScanHistoryItem> = emptyList(),
    val activeExport: ExportProgress? = null,
    val bannerMessage: String? = null
)

class DownloadsViewModel(
    private val prefsRepo: PrefsRepo,
    private val storageManager: StorageManager,
    private val historyRepository: HistoryRepository,
    private val exportProgressFlow: StateFlow<ExportProgress?>
) : ViewModel() {

    private val _uiState = MutableStateFlow(DownloadsUiState())
    val uiState: StateFlow<DownloadsUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            combine(
                prefsRepo.storagePreset,
                prefsRepo.safTreeUri,
                historyRepository.exportHistory,
                historyRepository.scanHistory,
                exportProgressFlow
            ) { preset, safUri, exports, scans, active ->
                _uiState.value.copy(
                    storagePreset = preset,
                    safTreeUri = safUri,
                    exports = exports,
                    scanHistory = scans,
                    activeExport = active
                )
            }.collect { next ->
                _uiState.value = next
            }
        }
    }

    fun selectPreset(preset: StoragePreset) {
        prefsRepo.setStoragePreset(preset)
        _uiState.update { it.copy(bannerMessage = "Save destination set to ${preset.label}") }
    }

    fun onSafFolderPicked(uri: Uri) {
        when (val res = storageManager.takePersistableSafPermission(uri)) {
            is AppResult.Success -> {
                _uiState.update { it.copy(bannerMessage = "Custom SAF folder connected.") }
            }
            is AppResult.Error -> {
                _uiState.update { it.copy(bannerMessage = res.message) }
            }
        }
    }

    fun deleteExport(record: ExportRecord) {
        storageManager.deleteMediaUri(record.contentUri)
        record.sidecarUri?.let { storageManager.deleteMediaUri(it) }
        historyRepository.removeExport(record.id)
        _uiState.update { it.copy(bannerMessage = "Removed ${record.fileName}") }
    }

    fun deleteScanItem(id: String) {
        historyRepository.removeScan(id)
    }

    fun dismissBanner() {
        _uiState.update { it.copy(bannerMessage = null) }
    }

    class Factory(
        private val prefsRepo: PrefsRepo,
        private val storageManager: StorageManager,
        private val historyRepository: HistoryRepository,
        private val exportProgressFlow: StateFlow<ExportProgress?>
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return DownloadsViewModel(prefsRepo, storageManager, historyRepository, exportProgressFlow) as T
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/ui/downloads/DownloadsScreen.kt": r'''
package com.clippulse.app.ui.downloads

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.VideoFile
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import com.clippulse.app.domain.model.ExportProgress
import com.clippulse.app.domain.model.ExportRecord
import com.clippulse.app.domain.model.ScanHistoryItem
import com.clippulse.app.domain.model.StoragePreset
import com.clippulse.app.service.ExportForegroundService
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.ui.theme.ClipPulseShapes
import com.clippulse.app.ui.theme.MonoTimestampStyle
import com.clippulse.app.util.UrlNormalizer
import com.clippulse.app.viewmodel.DownloadsViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun DownloadsScreen(
    viewModel: DownloadsViewModel,
    onRescanUrl: (String) -> Unit
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current

    val safPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocumentTree()
    ) { uri ->
        if (uri != null) {
            viewModel.onSafFolderPicked(uri)
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            StorageDestinationCard(
                activePreset = state.storagePreset,
                safTreeUri = state.safTreeUri,
                onSelectPreset = { preset ->
                    if (preset == StoragePreset.CUSTOM_SAF) {
                        safPicker.launch(null)
                    } else {
                        viewModel.selectPreset(preset)
                    }
                },
                onPickSafFolder = { safPicker.launch(null) }
            )
        }

        state.bannerMessage?.let { msg ->
            item {
                Surface(
                    shape = ClipPulseShapes.Chip,
                    color = ClipPulseColors.EmeraldAudio.copy(alpha = 0.14f),
                    border = BorderStroke(1.dp, ClipPulseColors.EmeraldAudio.copy(alpha = 0.45f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = msg,
                            color = ClipPulseColors.EmeraldAudio,
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f)
                        )
                        IconButton(
                            onClick = viewModel::dismissBanner,
                            modifier = Modifier.size(48.dp)
                        ) {
                            Icon(
                                Icons.Default.Close,
                                contentDescription = "Dismiss",
                                tint = ClipPulseColors.EmeraldAudio
                            )
                        }
                    }
                }
            }
        }

        state.activeExport?.let { progress ->
            item {
                ActiveExportCard(
                    progress = progress,
                    onCancel = { ExportForegroundService.cancelExport(context) },
                    onPlayOutput = { uriStr -> playClipUri(context, uriStr) }
                )
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Exported Clips (${state.exports.size})",
                    style = MaterialTheme.typography.titleMedium
                )
            }
        }

        if (state.exports.isEmpty()) {
            item {
                Surface(
                    shape = ClipPulseShapes.Card,
                    color = ClipPulseColors.Slate,
                    border = BorderStroke(1.dp, ClipPulseColors.Hairline),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Icon(
                            Icons.Default.VideoFile,
                            contentDescription = null,
                            tint = ClipPulseColors.TextMuted,
                            modifier = Modifier.size(32.dp)
                        )
                        Text(
                            text = "No exported clips yet",
                            style = MaterialTheme.typography.titleSmall
                        )
                        Text(
                            text = "Scan a video in Studio, trim a highlight, and tap Export to save MP4 + sidecar TXT.",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }
        } else {
            items(state.exports, key = { it.id }) { record ->
                ExportRecordCard(
                    record = record,
                    onPlay = { playClipUri(context, record.contentUri) },
                    onShare = { shareClipUri(context, record.contentUri, record.clipTitle) },
                    onDelete = { viewModel.deleteExport(record) }
                )
            }
        }

        if (state.scanHistory.isNotEmpty()) {
            item {
                Spacer(Modifier.height(6.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        Icons.Default.History,
                        contentDescription = null,
                        tint = ClipPulseColors.CyanAiPick,
                        modifier = Modifier.size(18.dp)
                    )
                    Text(
                        text = "Recent Scans (${state.scanHistory.size})",
                        style = MaterialTheme.typography.titleMedium
                    )
                }
            }

            items(state.scanHistory, key = { it.id }) { item ->
                ScanHistoryCard(
                    item = item,
                    onRescan = { onRescanUrl(item.sourceUrl) },
                    onDelete = { viewModel.deleteScanItem(item.id) }
                )
            }
        }
    }
}

@Composable
private fun StorageDestinationCard(
    activePreset: StoragePreset,
    safTreeUri: String,
    onSelectPreset: (StoragePreset) -> Unit,
    onPickSafFolder: () -> Unit
) {
    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Slate,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Save Location",
                        style = MaterialTheme.typography.titleMedium
                    )
                    Text(
                        text = if (activePreset == StoragePreset.CUSTOM_SAF && safTreeUri.isNotBlank()) {
                            "Custom SAF: ${Uri.decode(safTreeUri).takeLast(44)}"
                        } else {
                            "MediaStore: ${activePreset.relativePath}"
                        },
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                IconButton(
                    onClick = onPickSafFolder,
                    modifier = Modifier.size(48.dp)
                ) {
                    Icon(
                        Icons.Default.FolderOpen,
                        contentDescription = "Choose SAF folder",
                        tint = ClipPulseColors.Indigo
                    )
                }
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StoragePreset.entries.forEach { preset ->
                    val selected = preset == activePreset
                    FilterChip(
                        selected = selected,
                        onClick = { onSelectPreset(preset) },
                        label = { Text(preset.label) },
                        shape = ClipPulseShapes.Chip,
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = ClipPulseColors.Indigo,
                            selectedLabelColor = Color.White,
                            containerColor = ClipPulseColors.Elevated,
                            labelColor = ClipPulseColors.TextSecondary
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            enabled = true,
                            selected = selected,
                            borderColor = ClipPulseColors.Hairline,
                            selectedBorderColor = ClipPulseColors.Indigo
                        )
                    )
                }
            }
        }
    }
}

@Composable
private fun ActiveExportCard(
    progress: ExportProgress,
    onCancel: () -> Unit,
    onPlayOutput: (String) -> Unit
) {
    val borderColor = when {
        progress.error != null -> ClipPulseColors.CrimsonHeatmap
        progress.isRunning -> ClipPulseColors.Indigo
        else -> ClipPulseColors.EmeraldAudio
    }
    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Elevated,
        border = BorderStroke(1.dp, borderColor),
        modifier = Modifier.fillMaxWidth()
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
                Text(
                    text = progress.clipTitle,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                Text(
                    text = String.format(Locale.US, "%d%%", (progress.progress * 100f).toInt()),
                    style = MonoTimestampStyle,
                    color = borderColor
                )
            }
            Text(
                text = progress.error ?: progress.stage,
                style = MaterialTheme.typography.bodySmall,
                color = if (progress.error != null) ClipPulseColors.CrimsonHeatmap else ClipPulseColors.TextSecondary
            )
            if (progress.isRunning) {
                LinearProgressIndicator(
                    progress = { progress.progress.coerceIn(0f, 1f) },
                    color = ClipPulseColors.Indigo,
                    trackColor = ClipPulseColors.Obsidian,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(6.dp)
                )
                OutlinedButton(
                    onClick = onCancel,
                    shape = ClipPulseShapes.Chip,
                    border = BorderStroke(1.dp, ClipPulseColors.CrimsonHeatmap),
                    modifier = Modifier.height(48.dp)
                ) {
                    Text("Cancel Export", color = ClipPulseColors.CrimsonHeatmap)
                }
            } else if (!progress.outputUri.isNullOrBlank()) {
                Button(
                    onClick = { onPlayOutput(progress.outputUri) },
                    shape = ClipPulseShapes.Chip,
                    colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.EmeraldAudio),
                    modifier = Modifier.height(48.dp)
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Play Exported Clip", color = ClipPulseColors.Obsidian, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun ExportRecordCard(
    record: ExportRecord,
    onPlay: () -> Unit,
    onShare: () -> Unit,
    onDelete: () -> Unit
) {
    val sizeMb = record.fileSizeBytes.toDouble() / (1024.0 * 1024.0)
    val dateLabel = SimpleDateFormat("MMM d, HH:mm", Locale.US).format(Date(record.createdAtMs))

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
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = record.clipTitle,
                        style = MaterialTheme.typography.titleSmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = record.sourceTitle,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                IconButton(
                    onClick = onDelete,
                    modifier = Modifier.size(48.dp)
                ) {
                    Icon(
                        Icons.Default.DeleteOutline,
                        contentDescription = "Delete clip",
                        tint = ClipPulseColors.TextMuted
                    )
                }
            }

            Text(
                text = String.format(
                    Locale.US,
                    "%s • %.1f MB • %s • %s",
                    UrlNormalizer.formatTimestamp(record.durationSec),
                    sizeMb,
                    if (record.aspect9x16) "9:16" else "Original",
                    dateLabel
                ),
                style = MonoTimestampStyle,
                color = ClipPulseColors.TextSecondary
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Button(
                    onClick = onPlay,
                    shape = ClipPulseShapes.Chip,
                    colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.Indigo),
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Play")
                }

                OutlinedButton(
                    onClick = onShare,
                    shape = ClipPulseShapes.Chip,
                    border = BorderStroke(1.dp, ClipPulseColors.Hairline),
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                ) {
                    Icon(Icons.Default.Share, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Share")
                }
            }
        }
    }
}

@Composable
private fun ScanHistoryCard(
    item: ScanHistoryItem,
    onRescan: () -> Unit,
    onDelete: () -> Unit
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
                .padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.title,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                Text(
                    text = "${item.uploader} • ${UrlNormalizer.formatTimestamp(item.durationSec)} • ${item.clipCount} clips",
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            OutlinedButton(
                onClick = onRescan,
                shape = ClipPulseShapes.Chip,
                border = BorderStroke(1.dp, ClipPulseColors.Indigo),
                modifier = Modifier.height(48.dp)
            ) {
                Text("Scan")
            }
            IconButton(
                onClick = onDelete,
                modifier = Modifier.size(48.dp)
            ) {
                Icon(
                    Icons.Default.DeleteOutline,
                    contentDescription = "Remove history item",
                    tint = ClipPulseColors.TextMuted
                )
            }
        }
    }
}

private fun playClipUri(context: Context, uriString: String) {
    val intent = Intent(Intent.ACTION_VIEW).apply {
        setDataAndType(Uri.parse(uriString), "video/mp4")
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    runCatching {
        context.startActivity(Intent.createChooser(intent, "Play Clip"))
    }.onFailure {
        Toast.makeText(context, "No video player found to open this clip.", Toast.LENGTH_SHORT).show()
    }
}

private fun shareClipUri(context: Context, uriString: String, title: String) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "video/mp4"
        putExtra(Intent.EXTRA_STREAM, Uri.parse(uriString))
        putExtra(Intent.EXTRA_TEXT, title)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    runCatching {
        context.startActivity(Intent.createChooser(intent, "Share Clip"))
    }.onFailure {
        Toast.makeText(context, "Unable to share this clip.", Toast.LENGTH_SHORT).show()
    }
}
''',
}
