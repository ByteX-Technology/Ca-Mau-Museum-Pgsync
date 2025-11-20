import re
import logging
from pgsync.plugin import Plugin

logger = logging.getLogger('SearchFilterPlugin')


class SearchFilterPlugin(Plugin):
    name = 'SearchFilter'

    def transform(self, doc, **kwargs):
        """
        Transform document and mark as deleted if filter criteria not met.
        """
        operation = kwargs.get('operation')
        index = kwargs.get('index')
        logger.info(
            f"PLUGIN TRANSFORM: index={index}, id={doc.get('id')}, operation={operation}")

        # Always pass through actual delete operations
        if operation == 'delete':
            return doc

        # TuLieu detection (has LoaiTuLieu field)
        if 'LoaiTuLieu' in doc:
            result = self._process_tulieu(doc, kwargs)
            if result is None:
                return {'idGoc': doc.get('idGoc') or doc.get('id'), 'deleted': True}
            return result

        # NoiDung detection (has _nhom child)
        if '_nhom' in doc:
            result = self._process_noidung(doc, kwargs)
            if result is None:
                logger.warning(
                    f"NoiDung id={doc.get('id')} marked as deleted. TrangThai={doc.get('TrangThai')}, _nhom={doc.get('_nhom')}")
                return {'idGoc': doc.get('idGoc') or doc.get('id'), 'deleted': True}
            return result

        # BoSuuTap detection
        if '_tep' in doc and 'TieuDe' in doc and not doc.get('_artifact') and not doc.get('_relic') and not doc.get('_heritage'):
            result = self._process_bosuutap(doc, kwargs)
            if result is None:
                return {'idGoc': doc.get('idGoc') or doc.get('id'), 'deleted': True}
            return result

        # HoSo-based items (artifact, relic, heritage)
        trang_thai = doc.get('TrangThai', '')
        artifact = doc.get('_artifact')
        relic = doc.get('_relic')
        heritage = doc.get('_heritage')

        if artifact:
            result = self._process_artifact(doc, artifact, trang_thai, kwargs)
            if result is None:
                artifact_id = artifact.get('idGoc') if artifact else None
                return {'idGoc': artifact_id or doc.get('id'), 'deleted': True}
            return result
        elif relic:
            result = self._process_relic(doc, relic, trang_thai, kwargs)
            if result is None:
                relic_id = relic.get('idGoc') if relic else None
                return {'idGoc': relic_id or doc.get('id'), 'deleted': True}
            return result
        elif heritage:
            result = self._process_heritage(doc, heritage, trang_thai, kwargs)
            if result is None:
                heritage_id = heritage.get('idGoc') if heritage else None
                return {'idGoc': heritage_id or doc.get('id'), 'deleted': True}
            return result
        else:
            # No matching child record - mark as deleted
            return {'idGoc': doc.get('id'), 'deleted': True}

    def _process_noidung(self, doc, kwargs):
        """Process NoiDung (content) items with category filtering"""
        trang_thai = doc.get('TrangThai', '')
        if trang_thai != 'da_dang':
            return {
                'idGoc': doc.get('id'),
                'deleted': True
            }

        # Get NhomNoiDung data and validate it matches NhomNoiDungGocId
        # nhom_goc_id = doc.get('NhomNoiDungGocId')
        nhom = doc.get('_nhom', {})

        # PGSync bug workaround: verify _nhom.id matches NhomNoiDungGocId
        # if nhom_goc_id and nhom.get('id') != nhom_goc_id:
        #     # _nhom doesn't match - PGSync returned wrong NhomNoiDung
        #     logger.warning(f"NoiDung id={doc.get('id')}: _nhom.id={nhom.get('id')} != NhomNoiDungGocId={nhom_goc_id}, marking deleted")
        #     return {
        #         'idGoc': doc.get('id'),
        #         'deleted': True
        #     }

        # ten_he_thong = nhom.get('TenHeThong', '')
        # logger.info(f"NoiDung id={doc.get('id')}: TrangThai={trang_thai}, TenHeThong={ten_he_thong}, validated _nhom.id={nhom.get('id')}")

        # if ten_he_thong not in ['tin_tuc', 'trung_bay']:
        #     return {
        #         'idGoc': doc.get('id'),
        #         'deleted': True
        #     }

        result = {
            'idGoc': doc.get('idGoc') or doc.get('id'),
            'TieuDe': doc.get('TieuDe'),
            'MoTa': doc.get('MoTa'),
            'ThoiGianTao': doc.get('ThoiGianTao'),
            'ThoiGianCapNhat': doc.get('ThoiGianCapNhat'),
            'ThuocNhom': nhom.get('Ten', 'Nội dung'),
            'deleted': False
        }

        anh_dai_dien_id = doc.get('AnhDaiDienId')
        if anh_dai_dien_id:
            result['MaSoAnhDaiDien'] = anh_dai_dien_id

        return result

    def _process_bosuutap(self, doc, kwargs):
        """Process BoSuuTap (collection) items"""
        hoat_dong = doc.get('HoatDong')
        if hoat_dong != 1:
            return {
                'idGoc': doc.get('id'),
                'deleted': True
            }

        result = {
            'idGoc': doc.get('idGoc') or doc.get('id'),
            'TieuDe': doc.get('TieuDe'),
            'MoTa': doc.get('MoTa'),
            'ThoiGianTao': doc.get('ThoiGianTao'),
            'ThoiGianCapNhat': doc.get('ThoiGianCapNhat'),
            'ThuocNhom': 'Bộ sưu tập',
            'deleted': False
        }

        tep = doc.get('_tep', {})
        if tep:
            result['MaSoAnhDaiDien'] = tep.get('MaSoAnhDaiDien')
            result['KhoaAnhDaiDien'] = tep.get('KhoaAnhDaiDien')

        return result

    def _process_tulieu(self, doc, kwargs):
        """Process TuLieu (document) items"""
        hien_thi = doc.get('HienThi')
        if hien_thi != 1:
            return {
                'idGoc': doc.get('id'),
                'deleted': True
            }

        result = {
            'idGoc': doc.get('idGoc') or doc.get('id'),
            'TieuDe': doc.get('TieuDe'),
            'MoTa': doc.get('MoTaNgan') or '',  # Use MoTaNgan instead of MoTa
            'ThoiGianTao': doc.get('ThoiGianTao'),
            'ThoiGianCapNhat': doc.get('ThoiGianCapNhat'),
            'ThuocNhom': 'Tư liệu',
            'deleted': False
        }

        loai_tulieu = doc.get('LoaiTuLieu')
        loai_mapping = {
            'image': 'Hình ảnh',
            'video': 'Video',
            'file_document': 'Tài liệu',
            'text_document': 'Văn bản'
        }

        if loai_tulieu and loai_tulieu in loai_mapping:
            result['Nhan'] = [loai_mapping[loai_tulieu]]

        duong_dan = doc.get('DuongDanAnhDaiDien')
        if duong_dan:
            match = re.search(r'[?&]key=([^&]+)', duong_dan)
            if match:
                result['KhoaAnhDaiDien'] = match.group(1)

        return result

    def _process_artifact(self, doc, artifact, trang_thai, kwargs):
        """Process HienVat (artifact) items"""
        if trang_thai != 'da_duyet':
            return {
                'idGoc': artifact.get('idGoc') or artifact.get('id') or doc.get('id'),
                'deleted': True
            }

        result = {
            'idGoc': artifact.get('idGoc') or artifact.get('id'),
            'TieuDe': artifact.get('TieuDe'),
            'MoTa': artifact.get('MoTa'),
            'ThoiGianTao': doc.get('ThoiGianTao'),
            'ThoiGianCapNhat': doc.get('ThoiGianCapNhat'),
            'ThuocNhom': 'Hiện vật',
            'Nhan': [artifact.get('SoDangKy')],
            'deleted': False
        }

        hinh_anh_list = artifact.get('HinhAnhHienVat', [])
        if hinh_anh_list and len(hinh_anh_list) > 0:
            first_image = hinh_anh_list[0]
            tep = first_image.get('_tep', {})
            if tep:
                result['MaSoAnhDaiDien'] = tep.get('MaSoAnhDaiDien')
                result['KhoaAnhDaiDien'] = tep.get('KhoaAnhDaiDien')

        return result

    def _process_relic(self, doc, relic, trang_thai, kwargs):
        """Process DiTich (relic) items"""
        if trang_thai != 'da_duyet':
            return {
                'idGoc': (relic.get('idGoc') or relic.get('id')) if relic else doc.get('id'),
                'deleted': True
            }

        # Check if ChiTietDiTich exists
        # if not relic or not relic.get('id'):
        #     return {
        #         'idGoc': (relic.get('idGoc') or relic.get('id')) if relic else doc.get('id'),
        #         'deleted': True
        #     }

        result = {
            'idGoc': relic.get('idGoc') or relic.get('id'),
            'TieuDe': relic.get('TieuDe'),
            'MoTa': relic.get('MoTa') or '',
            'ThoiGianTao': doc.get('ThoiGianTao'),
            'ThoiGianCapNhat': doc.get('ThoiGianCapNhat'),
            'ThuocNhom': 'Di tích',
            'deleted': False
        }

        nhan_list = []

        # Add SoQuyetDinh from ChiTietDiTich if exists
        so_quyet_dinh_chitiet = relic.get('SoQuyetDinh', '')
        if so_quyet_dinh_chitiet:
            nhan_list.append(so_quyet_dinh_chitiet)

        # Add from HangDiTich array
        hang_list = relic.get('HangDiTich') or []
        for hang in hang_list:
            loai_hang = hang.get('_loaiHang', {})
            loai_hang_name = loai_hang.get('Nhan', '')
            if loai_hang_name:
                nhan_list.append(loai_hang_name)

            so_quyet_dinh = hang.get('SoQuyetDinh', '')
            if so_quyet_dinh:
                nhan_list.append(so_quyet_dinh)

        result['Nhan'] = nhan_list

        anh_list = relic.get('AnhDiTich') or []
        if anh_list and len(anh_list) > 0:
            first_image = anh_list[0]
            tep = first_image.get('_tep', {})
            if tep:
                result['MaSoAnhDaiDien'] = tep.get('MaSoAnhDaiDien')
                result['KhoaAnhDaiDien'] = tep.get('KhoaAnhDaiDien')

        return result

    def _process_heritage(self, doc, heritage, trang_thai, kwargs):
        """Process DiSan (heritage) items"""
        if trang_thai != 'da_duyet':
            return {
                'idGoc': heritage.get('idGoc') or heritage.get('id') or doc.get('id'),
                'deleted': True
            }

        result = {
            'idGoc': heritage.get('idGoc') or heritage.get('id'),
            'TieuDe': heritage.get('TieuDe'),
            'MoTa': heritage.get('MoTaNgan') or '',
            'ThoiGianTao': doc.get('ThoiGianTao'),
            'ThoiGianCapNhat': doc.get('ThoiGianCapNhat'),
            'ThuocNhom': 'Di sản văn hoá phi vật thể',
            'deleted': False
        }

        so_quyet_dinh = heritage.get('SoQuyetDinh', '')
        if so_quyet_dinh:
            result['Nhan'] = [so_quyet_dinh]
        else:
            result['Nhan'] = []

        # Extract avatar directly from AnhDaiDienId
        anh_dai_dien_id = heritage.get('AnhDaiDienId')
        if anh_dai_dien_id:
            result['MaSoAnhDaiDien'] = anh_dai_dien_id

        return result
